#!/usr/bin/env python3
"""Collect public Qidian bibliographic and catalog metadata from JSON endpoints.

No chapter content endpoint is called. No login cookie, CAPTCHA solving, stealth,
or access-control bypass is used.
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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/153 Safari/537.36"
INFO = "https://qqapp.qidian.com/ajax/book/info"
CATALOG = "https://qqapp.qidian.com/ajax/book/category"
BLOCK = (202, 401, 403, 429)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_db(root: Path) -> Path:
    hits = list(root.rglob("webnovel_catalog.sqlite"))
    if not hits:
        raise FileNotFoundError("webnovel_catalog.sqlite not found")
    return hits[0]


def choose_ids(db: Path, offset: int, limit: int):
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
    return [dict(rows[(start+i) % len(rows)]) for i in range(min(limit, len(rows)))]


def get_json(url: str, referer: str = "https://m.qidian.com/"):
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Referer": referer,
        },
    )
    with urlopen(req, timeout=20) as r:
        status = r.status
        body = r.read(20 * 1024 * 1024 + 1)
        ctype = r.headers.get("Content-Type", "")
    if len(body) > 20 * 1024 * 1024:
        raise ValueError("size_limit")
    if status != 200:
        raise HTTPError(url, status, "unexpected status", {}, None)
    obj = json.loads(body.decode("utf-8", "replace"))
    return status, ctype, body, obj


def info_fields(obj):
    data = obj.get("data") or {}
    b = data.get("bookInfo") or data.get("bookinfo") or data
    if not isinstance(b, dict):
        return {}
    labels = b.get("bookLabels") or []
    tags = []
    if isinstance(labels, list):
        for x in labels:
            if isinstance(x, dict) and x.get("tag"):
                tags.append(str(x["tag"]))
    return {
        "book_id": str(b.get("bookId") or b.get("bid") or ""),
        "title": b.get("bookName") or b.get("bName"),
        "author": b.get("authorName") or b.get("bAuth") or b.get("author"),
        "status": b.get("bookStatus"),
        "word_count": b.get("wordsCnt") or b.get("wordCount"),
        "update_time": b.get("updTime") or b.get("updateTime"),
        "latest_chapter": b.get("updChapterName") or b.get("lastChapterName"),
        "category": b.get("chanName") or b.get("categoryName"),
        "tags": tags,
        "description": b.get("desc"),
        "raw_keys": sorted(b.keys()),
    }


def flatten_catalog(obj, book_id):
    out = []
    data = obj.get("data") if isinstance(obj, dict) else None

    def walk(x, volume=None):
        if isinstance(x, dict):
            next_volume = volume
            for k in ("vN", "volumeName", "volume_name", "volName"):
                if x.get(k):
                    next_volume = str(x[k])
                    break
            cid = x.get("cU") or x.get("chapterId") or x.get("chapter_id") or x.get("id")
            title = x.get("cN") or x.get("chapterName") or x.get("chapter_name") or x.get("name")
            if cid is not None and title and (
                x.get("cU") is not None or
                x.get("chapterId") is not None or
                "chapter" in " ".join(str(k).lower() for k in x.keys())
            ):
                out.append({
                    "book_id": str(book_id),
                    "chapter_id": str(cid),
                    "chapter_title": str(title),
                    "volume": next_volume,
                    "vip": x.get("isVip") if "isVip" in x else x.get("vipStatus"),
                    "update_time": x.get("updateTime") or x.get("updTime"),
                })
            for v in x.values():
                walk(v, next_volume)
        elif isinstance(x, list):
            for v in x:
                walk(v, volume)

    walk(data)
    seen = set()
    clean = []
    for r in out:
        key = (r["chapter_id"], r["chapter_title"])
        if key in seen:
            continue
        seen.add(key)
        clean.append(r)
    return clean


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    seeds = choose_ids(find_db(Path(args.baseline)), args.offset, args.limit)
    (out/"seed_batch.json").write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")

    records = []
    chapters = []
    logs = []
    blocked = False

    for seed in seeds:
        wid = seed["platform_work_id"]
        rec = {"seed": seed, "work_id": wid, "observed_at": utcnow()}
        for kind, base in (("info", INFO), ("catalog", CATALOG)):
            url = base + "?" + urlencode({"bookId": wid})
            log = {"work_id": wid, "kind": kind, "url": url, "started_at": utcnow()}
            try:
                status, ctype, raw, obj = get_json(url)
                log.update(status=status, content_type=ctype, bytes=len(raw),
                           sha256=hashlib.sha256(raw).hexdigest())
                code = obj.get("code") if isinstance(obj, dict) else None
                log["api_code"] = code
                if kind == "info":
                    rec["info"] = info_fields(obj)
                    rec["info_api_code"] = code
                    (out/f"info_{wid}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
                else:
                    crows = flatten_catalog(obj, wid)
                    rec["catalog_api_code"] = code
                    rec["chapter_count"] = len(crows)
                    rec["first_chapter"] = crows[0] if crows else None
                    rec["last_chapter"] = crows[-1] if crows else None
                    chapters.extend(crows)
                    (out/f"catalog_{wid}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
            except HTTPError as e:
                log.update(status=e.code, error=repr(e))
                if e.code in BLOCK:
                    blocked = True
            except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as e:
                log["error"] = repr(e)
            logs.append(log)
            (out/"retrieval_log.json").write_text(json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8")
            if blocked:
                break
            time.sleep(max(args.delay, 2.0))
        records.append(rec)
        with (out/"qidian_api_metadata.jsonl").open("w", encoding="utf-8") as f:
            for x in records:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        with (out/"qidian_chapter_catalog.jsonl").open("w", encoding="utf-8") as f:
            for x in chapters:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        if blocked:
            break

    summary = {
        "requested_seed_count": len(seeds),
        "completed_work_count": len(records),
        "works_with_title": sum(bool((x.get("info") or {}).get("title")) for x in records),
        "chapter_rows": len(chapters),
        "blocked_stop": blocked,
        "created_at": utcnow(),
        "scope": "public bibliographic and chapter-catalog metadata only; no chapter content endpoint called",
    }
    (out/"summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
