#!/usr/bin/env python3
"""Collect public Qidian work/catalog metadata with a normal headless browser.

Scope: bibliographic and date metadata only. No chapter text is stored, no login
state is used, and challenge/CAPTCHA/access-control pages stop the batch.
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
    n = len(rows)
    start = offset % n
    out = []
    for i in range(min(limit, n)):
        out.append(dict(rows[(start + i) % n]))
    return out


def visible_date(label: str, text: str) -> str | None:
    m = re.search(re.escape(label) + r"\s*[:：]?\s*(" + DATE_RE.pattern + r")", text)
    return m.group(1) if m else None


def normalize_url(href: str | None) -> str | None:
    if not href:
        return None
    if href.startswith("//"):
        return "https:" + href
    if href.startswith("/"):
        return "https://www.qidian.com" + href
    return href


async def extract_page(page, work_id: str, kind: str) -> dict:
    body = ""
    try:
        body = await page.locator("body").inner_text(timeout=7000)
    except Exception:
        pass
    low = body.lower()
    challenged = any(token.lower() in low for token in CHALLENGE)

    html = await page.content()
    meta = await page.evaluate(
        """() => Object.fromEntries(
          Array.from(document.querySelectorAll('meta'))
            .map(m => [m.getAttribute('property') || m.getAttribute('name') || m.getAttribute('itemprop'), m.content])
            .filter(x => x[0] && x[1])
        )"""
    )
    h1 = None
    author = None
    try:
        h1 = (await page.locator("h1").first.inner_text(timeout=3000)).strip()
    except Exception:
        pass
    for sel in ("a[href*='/author/']", "a[href*='author']", ".writer a", ".book-info a"):
        try:
            val = (await page.locator(sel).first.inner_text(timeout=1200)).strip()
            if val:
                author = val
                break
        except Exception:
            continue

    status = None
    for token in ("已经完本", "完本", "连载中", "连载"):
        if token in body:
            status = token
            break
    word_count = None
    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*万字", body)
    if m:
        word_count = m.group(1) + "万字"

    key_times = []
    for m in KEY_TIME_RE.finditer(html):
        raw = m.group(1).strip()
        if raw not in key_times:
            key_times.append(raw)

    chapters = []
    if kind == "catalog":
        seen = set()
        anchors = await page.locator("a").all()
        for a in anchors:
            try:
                href = normalize_url(await a.get_attribute("href"))
                title = (await a.inner_text()).strip()
            except Exception:
                continue
            if not href or not title:
                continue
            parsed = urlparse(href)
            if str(work_id) not in href:
                continue
            if not any(x in parsed.path.lower() for x in ("/chapter/", "/read/", "/book/")):
                continue
            key = (href, title)
            if key in seen:
                continue
            seen.add(key)
            chapters.append({"title": title[:300], "url": href})
        if len(chapters) > 20000:
            chapters = chapters[:20000]

    ending = [x for x in chapters if ENDING_RE.search(x["title"])]
    return {
        "work_id": work_id,
        "page_kind": kind,
        "url": page.url,
        "observed_at": utcnow(),
        "challenged": challenged,
        "http_title": await page.title(),
        "title": h1,
        "author": author,
        "status": status,
        "word_count_visible": word_count,
        "visible_update_time": visible_date("更新时间", body),
        "visible_first_publish_time": visible_date("首发时间", body),
        "meta": {k: v for k, v in meta.items() if k and any(t in k.lower() for t in ("date", "time", "title", "author"))},
        "embedded_time_candidates": key_times[:100],
        "chapter_count_observed": len(chapters),
        "first_chapter": chapters[0] if chapters else None,
        "last_chapter": chapters[-1] if chapters else None,
        "ending_title_candidates": ending[-20:],
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
    log = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()

        for seed in seeds:
            wid = seed["platform_work_id"]
            item = {"seed": seed, "pages": []}
            blocked = False
            for kind, url in (
                ("work", f"https://www.qidian.com/book/{wid}/"),
                ("catalog", f"https://www.qidian.com/book/{wid}/catalog/"),
            ):
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
                        blocked = True
                except PlaywrightTimeoutError:
                    item["pages"].append({"work_id": wid, "page_kind": kind, "url": url, "observed_at": utcnow(), "error": "timeout"})
                except Exception as e:
                    item["pages"].append({"work_id": wid, "page_kind": kind, "url": url, "observed_at": utcnow(), "error": repr(e)})
                is_blocked = host in blocked_hosts\n                log.append({"work_id": wid, "kind": kind, "requested_url": url, "started_at": started, "status": status, "blocked": is_blocked})
                (out / "retrieval_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")
                await page.wait_for_timeout(args.delay_ms)
                if blocked:
                    break
            records.append(item)
            with (out / "qidian_metadata.jsonl").open("w", encoding="utf-8") as f:
                for r in records:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            if blocked:
                break
        await context.close()
        await browser.close()

    summary = {
        "requested_seed_count": len(seeds),
        "completed_work_count": len(records),
        "blocked_hosts": sorted(blocked_hosts),\n        "blocked_stop": len(blocked_hosts) >= 2,
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
