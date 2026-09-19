#!/usr/bin/env python3
"""Harvest one exhaustive JJWXC public catalog partition without deep-page login.

A top-level cell is year × originality × orientation × completion status.
If a cell has more than MAX_PAGES, it is recursively split using ordinary public
catalog filters (era, type, main-view, favorite-count bucket) until each leaf is
small enough to fetch using anonymous pages <= MAX_PAGES.

No login, CAPTCHA solving, or protected deep pagination is used.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode

from collect_catalog import Collector, BASE, parse_jjwxc

DIMENSIONS = [
    ("sd", [1, 2, 4, 5]),
    ("lx", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 17, 20, 18, 19, 21, 22, 23, 24, 25, 27]),
    ("mainview", [1, 2, 3, 4, 5, 8, 9, 12, 13]),
    ("novelbefavoritedcount", [1, 2, 3, 4, 5, 6]),
]


def filter_param(name: str, value: int) -> tuple[str, int]:
    return f"{name}{value}", value


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--yc", type=int, choices=[1, 2], required=True)
    ap.add_argument("--xx", type=int, choices=[1, 2, 3, 5, 6], required=True)
    ap.add_argument("--isfinish", type=int, choices=[1, 2], required=True)
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--request-budget", type=int, default=250)
    ap.add_argument("--delay", type=float, default=5)
    args = ap.parse_args()

    if not 2003 <= args.year <= 2026:
        ap.error("year out of range")
    if not 1 <= args.max_pages <= 10:
        ap.error("max-pages must stay within anonymous deep-page limit")
    if not 10 <= args.request_budget <= 1000:
        ap.error("invalid request budget")

    out = Path(args.out)
    fetcher = Collector(out, delay=args.delay)
    records_path = out / "jjwxc_partition_records.jsonl"
    records_path.write_text("", encoding="utf-8")

    base = {
        "version": 1,
        "fw1": 1,
        f"fbsj{args.year}": args.year,
        "sortType": 3,
        "isfinish": args.isfinish,
    }
    base.update(dict([filter_param("yc", args.yc), filter_param("xx", args.xx)]))

    seen = set()
    cells = []
    unresolved = []
    requests = 0
    accepted_rows = 0

    def fetch_cell(filters: dict[str, int], page: int, label: str):
        nonlocal requests
        if requests >= args.request_budget:
            return None, None, None
        params = {**base, **filters, "page": page}
        url = BASE + "?" + urlencode(params)
        name = f"{label}_p{page:02}.html"
        body = fetcher.get(url, name)
        requests += 1
        if body is None:
            return None, None, url
        rows, meta = parse_jjwxc(body, url, fetcher.logs[-1]["retrieved_at"])
        if rows and {r["declared_pub_year"] for r in rows} != {args.year}:
            raise ValueError(f"year validation failed for {url}")
        if meta["current_page"] not in (None, page):
            raise ValueError(f"page validation failed for {url}")
        return rows, meta, url

    def write_leaf(rows, filters, page, raw_file):
        nonlocal accepted_rows
        with records_path.open("a", encoding="utf-8") as fp:
            for pos, row in enumerate(rows, 1):
                wid = row["work_id"]
                key = (wid,)
                if key in seen:
                    continue
                seen.add(key)
                row.update(
                    partition_year=args.year,
                    partition_yc=args.yc,
                    partition_xx=args.xx,
                    partition_isfinish=args.isfinish,
                    partition_filters=filters,
                    partition_page=page,
                    row_on_partition_page=pos,
                    raw_file=raw_file,
                    selection_method="exhaustive_public_filter_leaf",
                )
                fp.write(json.dumps(row, ensure_ascii=False) + "\n")
                accepted_rows += 1

    def recurse(filters: dict[str, int], depth: int, path_code: str):
        if requests >= args.request_budget:
            unresolved.append({"filters": filters, "reason": "request_budget_exhausted", "depth": depth})
            return

        rows, meta, url = fetch_cell(filters, 1, path_code)
        if rows is None or meta is None:
            unresolved.append({"filters": filters, "reason": "fetch_failed", "depth": depth, "url": url})
            return

        total = meta.get("total_pages")
        cells.append({
            "filters": filters,
            "depth": depth,
            "total_pages": total,
            "rows_page1": len(rows),
            "url": url,
        })
        if not total:
            return

        if total <= args.max_pages:
            write_leaf(rows, filters, 1, f"{path_code}_p01.html")
            for page in range(2, total + 1):
                if requests >= args.request_budget:
                    unresolved.append({
                        "filters": filters,
                        "reason": "request_budget_exhausted_inside_leaf",
                        "next_page": page,
                        "total_pages": total,
                    })
                    return
                more, mmeta, _ = fetch_cell(filters, page, path_code)
                if more is None or mmeta is None:
                    unresolved.append({
                        "filters": filters,
                        "reason": "leaf_page_fetch_failed",
                        "page": page,
                        "total_pages": total,
                    })
                    return
                write_leaf(more, filters, page, f"{path_code}_p{page:02}.html")
            return

        if depth >= len(DIMENSIONS):
            unresolved.append({
                "filters": filters,
                "reason": "still_over_page_limit_after_all_public_partitions",
                "total_pages": total,
            })
            return

        dim, values = DIMENSIONS[depth]
        for value in values:
            if requests >= args.request_budget:
                unresolved.append({
                    "filters": filters,
                    "reason": "request_budget_exhausted_before_children",
                    "next_dimension": dim,
                })
                return
            key, val = filter_param(dim, value)
            child = {**filters, key: val}
            recurse(child, depth + 1, path_code + f"_{dim}{value}")

    root_filters = {}
    recurse(root_filters, 0, f"y{args.year}_yc{args.yc}_xx{args.xx}_f{args.isfinish}")

    summary = {
        "year": args.year,
        "yc": args.yc,
        "xx": args.xx,
        "isfinish": args.isfinish,
        "max_pages": args.max_pages,
        "request_budget": args.request_budget,
        "requests_used": requests,
        "accepted_unique_works": len(seen),
        "accepted_rows": accepted_rows,
        "cells_probed": len(cells),
        "unresolved_cells": len(unresolved),
        "blocked_stop": bool(fetcher.blocked_hosts),
        "scope": "public JJWXC catalog metadata only; protected deep pages not requested",
    }
    (out / "partition_cells.json").write_text(json.dumps(cells, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "unresolved_cells.json").write_text(json.dumps(unresolved, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
