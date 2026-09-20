#!/usr/bin/env python3
"""Parse saved public Qidian catalog HTML into source-observation CSV.

The script expects HTML saved from a public catalog/list page. It does not handle
login, CAPTCHA, anti-bot circumvention, or paid content.
"""

from __future__ import annotations

import argparse
import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

BASE_URL = "https://www.qidian.com/"
BOOK_ID_RE = re.compile(r"/book/(\d+)")
DATE_RE = re.compile(r"(20\d{2}|19\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})")


def clean(text: str | None) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def extract_book_id(url: str) -> str:
    m = BOOK_ID_RE.search(urlparse(url).path)
    return m.group(1) if m else ""


def first_date(text: str) -> str:
    m = DATE_RE.search(text)
    if not m:
        return ""
    y, mth, d = m.groups()
    return f"{int(y):04d}-{int(mth):02d}-{int(d):02d}"


def parse_cards(html: str, source_url: str, raw_file: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    observed_at = datetime.now(timezone.utc).isoformat()
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    # Qidian markup changes over time, so work links are the stable discovery unit.
    for a in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, a.get("href", ""))
        work_id = extract_book_id(href)
        if not work_id or work_id in seen:
            continue

        title = clean(a.get("title") or a.get_text(" ", strip=True))
        if not title:
            continue
        seen.add(work_id)

        container = a
        for _ in range(5):
            if container.parent is None:
                break
            container = container.parent
            text = clean(container.get_text(" ", strip=True))
            if len(text) >= 40:
                break
        block_text = clean(container.get_text(" ", strip=True))

        author_name = ""
        author_link = container.find("a", href=re.compile(r"author|/authors/|/writer/"))
        if author_link and author_link is not a:
            author_name = clean(author_link.get_text(" ", strip=True))

        out.append({
            "platform": "qidian",
            "work_id": work_id,
            "source_name": "Qidian public catalog",
            "source_url": source_url,
            "snapshot_date": "",
            "title_observed": title,
            "author_observed": author_name,
            "author_id_observed": "",
            "date_raw": first_date(block_text),
            "genre_raw": block_text,
            "status_raw": "",
            "word_count_raw": "",
            "retrieval_status": "parsed",
            "collection_timestamp": observed_at,
            "work_url": href,
            "raw_file": raw_file,
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    rows = parse_cards(
        args.html.read_text(encoding="utf-8", errors="replace"),
        args.source_url,
        str(args.html),
    )
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
