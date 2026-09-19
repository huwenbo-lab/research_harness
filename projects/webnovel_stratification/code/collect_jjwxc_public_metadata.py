#!/usr/bin/env python3
"""Collect public JJWXC work/chapter metadata without storing novel prose.

The work page contains a chapter table. Only bibliographic fields, chapter titles,
chapter URLs, word counts, and explicit publication/update timestamps are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from date_parser_v04 import parse_jj_detail

UA = "WebnovelBibliographyResearch/0.5 (+https://github.com/huwenbo-lab/research_harness)"
CHALLENGE = ("验证码", "请登录后再访问", "请登入后再访问", "访问过于频繁", "安全验证")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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
        WHERE platform='jjwxc'
          AND platform_work_id GLOB '[0-9]*'
          AND genre_raw IS NOT NULL
          AND genre_raw LIKE '%-%'
        ORDER BY COALESCE(platform_declared_pub_year,9999), CAST(platform_work_id AS INTEGER)
        """
    ).fetchall()
    con.close()
    if not rows:
        return []
    n = len(rows)
    start = offset % n
    return [dict(rows[(start + i) % n]) for i in range(min(limit, n))]


def choose_seed_file(path: Path, offset: int, limit: int) -> list[dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        wid = str(r.get("platform_work_id") or r.get("work_id") or "").strip()
        if not wid.isdigit():
            continue
        if "jjwxc" == "jjwxc":
            genre = r.get("genre_raw") or r.get("genre")
            if genre is not None and "-" not in str(genre):
                continue
        rows[wid] = {
            "platform_work_id": wid,
            "title": r.get("title"),
            "author": r.get("author"),
            "status_raw": r.get("status_raw") or r.get("status"),
            "work_url": r.get("work_url"),
        }
    ordered = [rows[k] for k in sorted(rows, key=lambda x: int(x))]
    if not ordered:
        return []
    start = offset % len(ordered)
    return [ordered[(start + i) % len(ordered)] for i in range(min(limit, len(ordered)))]


def robots_allowed() -> tuple[bool, float]:
    url = "https://www.jjwxc.net/robots.txt"
    with urlopen(Request(url, headers={"User-Agent": UA}), timeout=20) as r:
        body = r.read(1024 * 1024)
    if b"<html" in body[:1000].lower() or b"<script" in body[:1000].lower():
        return False, 6.0
    rp = RobotFileParser()
    rp.parse(body.decode("utf-8", "replace").splitlines())
    allowed = rp.can_fetch("WebnovelBibliographyResearch", "https://www.jjwxc.net/onebook.php?novelid=1")
    delay = max(6.0, float(rp.crawl_delay("WebnovelBibliographyResearch") or 0))
    return allowed, delay


def completion_candidates(parsed: dict) -> list[dict]:
    out = []
    for ch in parsed.get("chapters", []):
        role = ch.get("end_role")
        if not role:
            continue
        pub = ch.get("publish_time_as_supplied")
        upd = ch.get("update_time_as_supplied")
        out.append(
            {
                "chapter_number": ch.get("chapter_number_raw"),
                "chapter_title": ch.get("chapter_title"),
                "role": role,
                "date_candidate": pub or upd,
                "basis": "explicit_chapter_publication" if pub else "chapter_update_only",
            }
        )
    return out


def compact(parsed: dict, html_hash: str, html_bytes: int, seed: dict, url: str) -> dict:
    chapters = parsed.get("chapters", [])
    first = chapters[0] if chapters else None
    last = chapters[-1] if chapters else None
    endings = completion_candidates(parsed)
    status = parsed.get("status") or seed.get("status_raw")
    if status and any(x in status for x in ("完结", "已完成")) and last:
        candidate_date = last.get("publish_time_as_supplied") or last.get("update_time_as_supplied")
        if candidate_date:
            endings.append({
                "chapter_number": last.get("chapter_number_raw"),
                "chapter_title": last.get("chapter_title"),
                "role": "completed_status_last_visible_chapter",
                "date_candidate": candidate_date,
                "basis": "explicit_chapter_publication_under_completed_status"
                         if last.get("publish_time_as_supplied")
                         else "chapter_update_under_completed_status",
            })
    return {
        "work_id": parsed.get("work_id"),
        "title": parsed.get("title") or seed.get("title"),
        "author": parsed.get("author") or seed.get("author"),
        "status": status,
        "url": url,
        "observed_at": utcnow(),
        "chapter_count_observed": len(chapters),
        "first_chapter_publication_date": first.get("publish_time_as_supplied") if first else None,
        "first_chapter_update_date": first.get("update_time_as_supplied") if first else None,
        "last_chapter_publication_date": last.get("publish_time_as_supplied") if last else None,
        "last_chapter_update_date": last.get("update_time_as_supplied") if last else None,
        "completion_candidates": endings,
        "date_meta": parsed.get("date_meta"),
        "metadata_lines": parsed.get("metadata_lines"),
        "chapters": chapters,
        "html_sha256": html_hash,
        "html_bytes_transient": html_bytes,
        "note": "Work-page HTML parsed transiently; no novel/chapter prose retained.",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline")
    ap.add_argument("--seed-file")
    ap.add_argument("--out", required=True)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    if args.seed_file:\n        seeds = choose_seed_file(Path(args.seed_file), args.offset, args.limit)\n    elif args.baseline:\n        seeds = choose_ids(find_db(Path(args.baseline)), args.offset, args.limit)\n    else:\n        ap.error("one of --seed-file or --baseline is required")
    (out / "seed_batch.json").write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")

    allowed, delay = robots_allowed()
    if not allowed:
        raise SystemExit("robots_not_permitted_or_unavailable")

    records = []
    logs = []
    blocked = False
    for seed in seeds:
        wid = seed["platform_work_id"]
        url = f"https://www.jjwxc.net/onebook.php?novelid={wid}"
        log = {"work_id": wid, "url": url, "started_at": utcnow()}
        try:
            with urlopen(Request(url, headers={"User-Agent": UA}), timeout=25) as r:
                status = r.status
                body = r.read(25 * 1024 * 1024 + 1)
            log.update(status=status, bytes=len(body))
            if len(body) > 25 * 1024 * 1024:
                raise ValueError("size_limit")
            text = BeautifulSoup(body, "html.parser").get_text(" ", strip=True)
            if status in (202, 401, 403, 429) or any(x in text for x in CHALLENGE):
                blocked = True
                log["blocked"] = True
            else:
                parsed = parse_jj_detail(body, wid, url)
                rec = compact(
                    parsed,
                    hashlib.sha256(body).hexdigest(),
                    len(body),
                    seed,
                    url,
                )
                records.append(rec)
                log["parsed_chapters"] = rec["chapter_count_observed"]
        except HTTPError as e:
            log.update(status=e.code, error=repr(e))
            if e.code in (202, 401, 403, 429):
                blocked = True
                log["blocked"] = True
        except Exception as e:
            log["error"] = repr(e)

        logs.append(log)
        (out / "retrieval_log.json").write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
        with (out / "jjwxc_detail_metadata.jsonl").open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if blocked:
            break
        time.sleep(delay)

    summary = {
        "requested_seed_count": len(seeds),
        "completed_work_count": len(records),
        "blocked_stop": blocked,
        "created_at": utcnow(),
        "scope": "public bibliographic/chapter/date metadata only; no novel prose retained",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
