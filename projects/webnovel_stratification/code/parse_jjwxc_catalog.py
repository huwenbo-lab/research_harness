#!/usr/bin/env python3
"""Parse saved JJWXC catalog HTML into a source-observation CSV.

This script deliberately separates *retrieval* from *parsing*. Save public catalog
pages as HTML first (manually or with a separate, rate-limited fetch step), then
parse them reproducibly. It does not bypass authentication, CAPTCHA, paywalls, or
other access controls.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup

BASE_URL = "https://www.jjwxc.net/"
DATE_RE = re.compile(r"(20\d{2}|19\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")
NUMBER_RE = re.compile(r"[\d,]+")


def clean(text: str | None) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def query_id(url: str, keys: tuple[str, ...]) -> str:
    query = parse_qs(urlparse(url).query)
    for key in keys:
        vals = query.get(key)
        if vals:
            return vals[0]
    return ""


def first_date(text: str) -> str:
    m = DATE_RE.search(text)
    if not m:
        return ""
    y, mth, d = m.groups()
    return f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"


def parse_rows(html: str, source_url: str, raw_file: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    observed_at = datetime.now(timezone.utc).isoformat()
    out: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for row in soup.find_all("tr"):
        links = row.find_all("a", href=True)
        work_link = None
        for a in links:
            href = a.get("href", "")
            if "novelid=" in href or "onebook.php" in href:
                work_link = a
                break
        if not work_link:
            continue

        work_url = urljoin(BASE_URL, work_link["href"])
        work_id = query_id(work_url, ("novelid", "id"))
        title = clean(work_link.get_text(" ", strip=True))
        if not work_id or not title:
            continue

        author_name = ""
        author_id = ""
        for a in links:
            href = urljoin(BASE_URL, a.get("href", ""))
            if "authorid=" in href or "oneauthor.php" in href:
                author_name = clean(a.get_text(" ", strip=True))
                author_id = query_id(href, ("authorid", "id"))
                break

        cells = [clean(td.get_text(" ", strip=True)) for td in row.find_all(["td", "th"])]
        row_text = " | ".join(cells)
        date_observed = first_date(row_text)

        key = (work_id, source_url)
        if key in seen:
            continue
        seen.add(key)

        out.append({
            "platform": "jjwxc",
            "work_id": work_id,
            "source_name": "JJWXC official catalog",
            "source_url": source_url,
            "snapshot_date": "",
            "title_observed": title,
            "author_observed": author_name,
            "author_id_observed": author_id,
            "date_raw": date_observed,
            "genre_raw": row_text,
            "status_raw": "",
            "word_count_raw": "",
            "retrieval_status": "parsed",
            "collection_timestamp": observed_at,
            "work_url": work_url,
            "raw_file": raw_file,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path, help="Saved JJWXC catalog HTML")
    ap.add_argument("--source-url", required=True, help="Exact catalog URL used to obtain the HTML")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    html = args.html.read_text(encoding="utf-8", errors="replace")
    rows = parse_rows(html, args.source_url, str(args.html))
    args.output.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "platform", "work_id", "source_name", "source_url", "snapshot_date",
        "title_observed", "author_observed", "author_id_observed", "date_raw",
        "genre_raw", "status_raw", "word_count_raw", "retrieval_status",
        "collection_timestamp", "work_url", "raw_file",
    ]
    with args.output.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"parsed_rows={len(rows)} output={args.output}")


if __name__ == "__main__":
    main()
