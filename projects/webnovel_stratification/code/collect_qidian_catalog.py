#!/usr/bin/env python3
"""Discover Qidian works from the public mobile category library.

Collects bibliographic listing JSON only. It never requests chapter content and
does not use login credentials or bypass challenge pages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor

BASE = "https://m.qidian.com/webcommon/category/list"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
BLOCK = (202, 401, 403, 429)
MALE_CATEGORIES = {
    "21": "玄幻", "22": "仙侠", "4": "都市", "15": "现实", "5": "历史",
    "7": "游戏", "9": "科幻", "10": "悬疑", "12": "N次元",
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_session(gender: str):
    jar = CookieJar()
    opener = build_opener(HTTPCookieProcessor(jar))
    prime = f"https://m.qidian.com/category/{gender}"
    req = Request(
        prime,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
        },
    )
    with opener.open(req, timeout=20) as r:
        body = r.read(3 * 1024 * 1024)
        if r.status != 200:
            raise HTTPError(prime, r.status, "prime failed", {}, None)
    token = next((cookie.value for cookie in jar if cookie.name == "_csrfToken"), "")
    return opener, token, hashlib.sha256(body).hexdigest()


def fetch_json(opener, url: str, referer: str):
    req = Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    with opener.open(req, timeout=20) as r:
        status = r.status
        ctype = r.headers.get("Content-Type", "")
        body = r.read(10 * 1024 * 1024 + 1)
    if len(body) > 10 * 1024 * 1024:
        raise ValueError("size_limit")
    if status != 200:
        raise HTTPError(url, status, "unexpected status", {}, None)
    return status, ctype, body, json.loads(body.decode("utf-8", "replace"))


def parse(payload, gender: str, cat_id: str, page: int):
    if not isinstance(payload, dict):
        return [], {}
    data = payload.get("data") or {}
    raw_rows = data.get("records") or []
    rows = []
    for pos, item in enumerate(raw_rows, 1):
        if not isinstance(item, dict):
            continue
        bid = str(item.get("bid") or item.get("bookId") or "").strip()
        title = str(item.get("bName") or item.get("bookName") or "").strip()
        if not bid.isdigit() or not title:
            continue
        rows.append(
            {
                "platform": "qidian",
                "work_id": bid,
                "title": title,
                "author": item.get("bAuth") or item.get("author"),
                "category": item.get("cat") or MALE_CATEGORIES.get(cat_id),
                "subcategory": item.get("subCat"),
                "status": item.get("state"),
                "word_count_raw": item.get("cnt"),
                "description": item.get("desc"),
                "audience_channel": gender,
                "requested_cat_id": cat_id,
                "page_num": page,
                "row_on_page": pos,
                "work_url": f"https://m.qidian.com/book/{bid}/",
                "source_type": "official_mobile_category_library",
                "raw_record": item,
            }
        )
    meta = {
        "code": payload.get("code"),
        "msg": payload.get("msg"),
        "total": data.get("total"),
        "pageNum": data.get("pageNum"),
        "pageSize": data.get("pageSize"),
        "isLast": data.get("isLast"),
        "records": len(raw_rows),
    }
    return rows, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--gender", choices=["male", "female"], default="male")
    ap.add_argument("--start-page", type=int, default=1)
    ap.add_argument("--pages", type=int, default=2)
    ap.add_argument("--cat-ids", default="")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--size", choices=["", "1", "2", "3", "4", "5"], default="")
    ap.add_argument("--isfinish", choices=["", "1", "2"], default="")
    args = ap.parse_args()

    if args.start_page < 1 or not 1 <= args.pages <= 200:
        ap.error("invalid page bounds")

    if args.cat_ids:
        cat_ids = [x.strip() for x in args.cat_ids.split(",") if x.strip().isdigit()]
    elif args.gender == "male":
        cat_ids = list(MALE_CATEGORIES)
    else:
        cat_ids = []
    if not cat_ids:
        raise ValueError("No validated category IDs supplied for this channel")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)

    records = []
    logs = []
    page_meta = []
    seen = set()
    blocked = False

    try:
        opener, csrf, prime_sha = make_session(args.gender)
        logs.append(
            {
                "kind": "session_prime",
                "gender": args.gender,
                "status": 200,
                "csrf_obtained": bool(csrf),
                "sha256": prime_sha,
                "retrieved_at": utcnow(),
            }
        )
    except Exception as exc:
        opener = None
        csrf = ""
        logs.append(
            {
                "kind": "session_prime",
                "gender": args.gender,
                "error": repr(exc),
                "retrieved_at": utcnow(),
            }
        )

    for cat_id in cat_ids:
        if blocked:
            break
        for page in range(args.start_page, args.start_page + args.pages):
            params = {"catId": cat_id, "pageNum": str(page), "gender": args.gender}
            if args.size:
                params["size"] = args.size
            if args.isfinish:
                params["isfinish"] = args.isfinish
            if csrf:
                params["_csrfToken"] = csrf
            url = BASE + "?" + urlencode(params)
            referer = f"https://m.qidian.com/category/catid{cat_id}/"
            log = {
                "kind": "category_page",
                "url": url,
                "gender": args.gender,
                "cat_id": cat_id,
                "page": page,
                "size": args.size or None,
                "isfinish": args.isfinish or None,
                "started_at": utcnow(),
            }
            try:
                if opener is None:
                    raise ValueError("session_prime_failed")
                status, ctype, body, obj = fetch_json(opener, url, referer)
                rows, meta = parse(obj, args.gender, cat_id, page)
                log.update(
                    status=status,
                    content_type=ctype,
                    bytes=len(body),
                    sha256=hashlib.sha256(body).hexdigest(),
                    api_code=meta.get("code"),
                    records=len(rows),
                )
                page_meta.append(
                    {"gender": args.gender, "cat_id": cat_id, "page": page, **meta}
                )
                (out / f"{args.gender}_cat{cat_id}_p{page:06}.json").write_text(
                    json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                for row in rows:
                    key = (row["audience_channel"], row["work_id"])
                    if key in seen:
                        continue
                    seen.add(key)
                    records.append(row)
                if meta.get("isLast") or not rows:
                    logs.append(log)
                    break
            except HTTPError as exc:
                log.update(status=exc.code, error=repr(exc))
                if exc.code in BLOCK:
                    blocked = True
            except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
                log["error"] = repr(exc)
            logs.append(log)
            if blocked:
                break
            time.sleep(max(2.0, args.delay))

    with (out / "qidian_catalog_records.jsonl").open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    (out / "retrieval_log.json").write_text(
        json.dumps(logs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    summary = {
        "gender": args.gender,
        "category_ids": cat_ids,
        "start_page": args.start_page,
        "size": args.size or None,
        "isfinish": args.isfinish or None,
        "requested_pages_per_category": args.pages,
        "completed_page_requests": len(page_meta),
        "unique_works": len(records),
        "page_meta": page_meta,
        "blocked_stop": blocked,
        "csrf_obtained": bool(csrf),
        "created_at": utcnow(),
        "scope": "official mobile category bibliographic metadata only",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
