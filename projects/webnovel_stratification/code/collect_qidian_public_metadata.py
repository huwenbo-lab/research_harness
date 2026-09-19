#!/usr/bin/env python3
"""Collect public Qidian bibliographic/date metadata with a normal browser.

No chapter prose is stored. No login state, CAPTCHA solving, stealth plugins, or
access-control bypass is used. A challenged host is skipped for the rest of the batch.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

DATE_RE = re.compile(r"(?:19|20)\d{2}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?")
KEY_TIME_RE = re.compile(
    r'["\'](?:publishTime|createTime|updateTime|firstPublishTime|lastUpdateTime|bookUpdateTime)["\']\s*:\s*["\']?([^,"\'}\]]{6,40})',
    re.I,
)
CHALLENGE = (
    "安全验证", "验证码", "访问过于频繁", "请求异常", "请完成验证",
    "verify you are human", "captcha", "challenge",
)
ENDING_RE = re.compile(r"全文完|全书完|正文完|终章|大结局|完结章")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", "replace")).hexdigest()


def find_db(root: Path) -> Path:
    hits = list(root.rglob("webnovel_catalog.sqlite"))
    if not hits:
        raise FileNotFoundError("webnovel_catalog.sqlite not found")
    return hits[0]


def choose_ids(db: Path, offset: int, limit: int) -> list[dict]:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT platform_work_id,title,author,status_raw,work_url
        FROM work_master
        WHERE platform='qidian' AND platform_work_id GLOB '[0-9]*'
        ORDER BY CAST(platform_work_id AS INTEGER)
        """
    ).fetchall()
    con.close()
    if not rows:
        return []
    start = offset % len(rows)
    return [dict(rows[(start + i) % len(rows)]) for i in range(min(limit, len(rows)))]


def visible_date(label: str, text: str) -> str | None:
    m = re.search(re.escape(label) + r"\s*[:：]?\s*(" + DATE_RE.pattern + r")", text)
    return m.group(1) if m else None


def normalize_url(href: str | None, current_host: str) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://" + current_host + href
    return href


async def extract_page(page, work_id: str, kind: str) -> dict:
    try:
        body = await page.locator("body").inner_text(timeout=7000)
    except Exception:
        body = ""
    challenged = any(token.lower() in body.lower() for token in CHALLENGE)
    html = await page.content()

    meta = await page.evaluate(
        """() => Object.fromEntries(
          Array.from(document.querySelectorAll('meta'))
            .map(m => [m.getAttribute('property') || m.getAttribute('name') || m.getAttribute('itemprop'), m.content])
            .filter(x => x[0] && x[1])
        )"""
    )

    title = None
    author = None
    try:
        title = (await page.locator("h1").first.inner_text(timeout=2500)).strip()
    except Exception:
        pass
    for sel in ("a[href*='/author/']", "a[href*='author']", ".writer a", ".book-info a"):
        try:
            val = (await page.locator(sel).first.inner_text(timeout=1000)).strip()
            if val:
                author = val
                break
        except Exception:
            continue

    status = next((x for x in ("已经完本", "完本", "连载中", "连载") if x in body), None)
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万字", body)
    word_count = (m.group(1) + "万字") if m else None

    embedded_times = []
    for m in KEY_TIME_RE.finditer(html):
        raw = m.group(1).strip()
        if raw not in embedded_times:
            embedded_times.append(raw)

    chapters = []
    if kind in ("catalog", "legacy_work"):
        seen = set()
        current_host = urlparse(page.url).hostname or "www.qidian.com"
        for a in await page.locator("a").all():
            try:
                href = normalize_url(await a.get_attribute("href"), current_host)
                ch_title = (await a.inner_text()).strip()
            except Exception:
                continue
            if not href or not ch_title or str(work_id) not in href:
                continue
            path = urlparse(href).path.lower()
            if not any(x in path for x in ("/chapter/", "/read/", "/book/")):
                continue
            key = (href, ch_title)
            if key in seen:
                continue
            seen.add(key)
            chapters.append({"title": ch_title[:300], "url": href})
            if len(chapters) >= 20000:
                break

    return {
        "work_id": work_id,
        "page_kind": kind,
        "url": page.url,
        "observed_at": utcnow(),
        "challenged": challenged,
        "http_title": await page.title(),
        "title": title,
        "author": author,
        "status": status,
        "word_count_visible": word_count,
        "visible_update_time": visible_date("更新时间", body),
        "visible_first_publish_time": visible_date("首发时间", body),
        "visible_date_candidates": list(dict.fromkeys(DATE_RE.findall(body)))[:200],
        "meta": {
            k: v for k, v in meta.items()
            if k and any(t in k.lower() for t in ("date", "time", "title", "author"))
        },
        "embedded_time_candidates": embedded_times[:100],
        "chapter_count_observed": len(chapters),
        "first_chapter": chapters[0] if chapters else None,
        "last_chapter": chapters[-1] if chapters else None,
        "ending_title_candidates": [x for x in chapters if ENDING_RE.search(x["title"])][-20:],
        "html_sha256": sha256_text(html),
        "html_bytes_transient": len(html.encode("utf-8", "replace")),
        "note": "HTML used transiently for metadata extraction only; novel/chapter prose is not stored.",
    }


async def collect(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    seeds = choose_ids(find_db(Path(args.baseline)), args.offset, args.limit)
    (out / "seed_batch.json").write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")
    records = []
    logs = []
    blocked_hosts: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()

        for seed in seeds:
            wid = seed["platform_work_id"]
            item = {"seed": seed, "pages": []}
            targets = (
                ("legacy_work", f"https://book.qidian.com/info/{wid}/"),
                ("legacy_honor", f"https://book.qidian.com/honor/{wid}/"),
                ("work", f"https://www.qidian.com/book/{wid}/"),
                ("catalog", f"https://www.qidian.com/book/{wid}/catalog/"),
            )
            for kind, url in targets:
                host = urlparse(url).hostname or ""
                if host in blocked_hosts:
                    continue
                started = utcnow()
                status = None
                try:
                    response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    status = response.status if response else None
                    await page.wait_for_timeout(args.wait_ms)
                    rec = await extract_page(page, wid, kind)
                    rec["http_status"] = status
                    item["pages"].append(rec)
                    if status in (202, 401, 403, 429) or rec["challenged"]:
                        blocked_hosts.add(host)
                except PlaywrightTimeoutError:
                    item["pages"].append({
                        "work_id": wid, "page_kind": kind, "url": url,
                        "observed_at": utcnow(), "error": "timeout",
                    })
                except Exception as e:
                    item["pages"].append({
                        "work_id": wid, "page_kind": kind, "url": url,
                        "observed_at": utcnow(), "error": repr(e),
                    })

                logs.append({
                    "work_id": wid,
                    "kind": kind,
                    "requested_url": url,
                    "started_at": started,
                    "status": status,
                    "blocked": host in blocked_hosts,
                })
                (out / "retrieval_log.json").write_text(
                    json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                await page.wait_for_timeout(args.delay_ms)

            records.append(item)
            with (out / "qidian_metadata.jsonl").open("w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")

            if "book.qidian.com" in blocked_hosts and "www.qidian.com" in blocked_hosts:
                break

        await context.close()
        await browser.close()

    summary = {
        "requested_seed_count": len(seeds),
        "completed_work_count": len(records),
        "blocked_hosts": sorted(blocked_hosts),
        "blocked_stop": "book.qidian.com" in blocked_hosts and "www.qidian.com" in blocked_hosts,
        "created_at": utcnow(),
        "scope": "public bibliographic/catalog/date metadata only; no novel prose retained",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=12)
    ap.add_argument("--wait-ms", type=int, default=2500)
    ap.add_argument("--delay-ms", type=int, default=5000)
    args = ap.parse_args()
    asyncio.run(collect(args))


if __name__ == "__main__":
    main()
