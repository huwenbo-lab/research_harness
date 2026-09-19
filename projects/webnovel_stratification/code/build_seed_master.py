#!/usr/bin/env python3
"""Build persistent platform seed masters from the baseline catalog plus new harvests.

Outputs one JSONL row per platform work ID. Only bibliographic metadata is merged.
New official catalog observations may fill missing title/author/status/genre/url but
never overwrite a nonempty baseline value solely because they were observed later.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def clean(value):
    if value is None:
        return None
    value = " ".join(str(value).replace("\xa0", " ").split())
    return value or None


def put(store, platform, row, source):
    wid = str(row.get("platform_work_id") or row.get("work_id") or "").strip()
    if not wid.isdigit():
        return
    if platform == "jjwxc":
        genre = row.get("genre_raw") or row.get("genre")
        if genre is not None and "-" not in str(genre):
            return
    key = (platform, wid)
    out = store.setdefault(key, {
        "platform": platform,
        "platform_work_id": wid,
        "title": None,
        "author": None,
        "status_raw": None,
        "genre_raw": None,
        "work_url": None,
        "declared_pub_year": None,
        "seed_sources": [],
    })
    mapping = {
        "title": ["title", "title_current"],
        "author": ["author", "author_name_current"],
        "status_raw": ["status_raw", "status"],
        "genre_raw": ["genre_raw", "category", "genre"],
        "work_url": ["work_url"],
        "declared_pub_year": ["declared_pub_year", "platform_declared_pub_year", "requested_year"],
    }
    for target, keys in mapping.items():
        if out.get(target) not in (None, ""):
            continue
        for k in keys:
            value = row.get(k)
            if value not in (None, ""):
                if target == "declared_pub_year":
                    try:
                        value = int(value)
                    except Exception:
                        value = None
                else:
                    value = clean(value)
                if value not in (None, ""):
                    out[target] = value
                    break
    if source not in out["seed_sources"]:
        out["seed_sources"].append(source)


def load_existing(store, path, platform):
    if not path or not Path(path).exists():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            put(store, platform, json.loads(line), "existing_master")


def load_baseline(store, root):
    hits = list(Path(root).rglob("webnovel_catalog.sqlite"))
    if not hits:
        raise FileNotFoundError("baseline webnovel_catalog.sqlite not found")
    con = sqlite3.connect(hits[0])
    con.row_factory = sqlite3.Row
    rows = con.execute("""
      SELECT platform,platform_work_id,title,author,status_raw,genre_raw,work_url,
             platform_declared_pub_year
      FROM work_master
      WHERE platform IN ('qidian','jjwxc')
    """).fetchall()
    con.close()
    for r in rows:
        d = dict(r)
        if d["platform"] == "jjwxc" and (not d.get("genre_raw") or "-" not in str(d["genre_raw"])):
            continue
        put(store, d["platform"], d, "baseline_v04")


def load_harvests(store, root):
    root = Path(root)
    patterns = {
        "qidian": [
            "qidian_catalog_records.jsonl",
        ],
        "jjwxc": [
            "jjwxc_partition_records.jsonl",
            "jjwxc_observations.jsonl",
            "catalog_observations.jsonl",
        ],
    }
    loaded = []
    for platform, names in patterns.items():
        for name in names:
            for path in root.rglob(name):
                count = 0
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    put(store, platform, row, "harvest:" + path.name)
                    count += 1
                loaded.append({"platform": platform, "file": str(path), "rows_read": count})
    return loaded


def write_platform(store, platform, path):
    rows = [v for (p, _), v in store.items() if p == platform]
    rows.sort(key=lambda r: int(r["platform_work_id"]))
    with Path(path).open("w", encoding="utf-8") as fp:
        for r in rows:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--harvest-root", required=True)
    ap.add_argument("--existing-qidian")
    ap.add_argument("--existing-jjwxc")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=False)
    store = {}
    load_existing(store, args.existing_qidian, "qidian")
    load_existing(store, args.existing_jjwxc, "jjwxc")
    load_baseline(store, args.baseline)
    loaded = load_harvests(store, args.harvest_root)

    qn = write_platform(store, "qidian", out / "qidian-seeds.jsonl")
    jn = write_platform(store, "jjwxc", out / "jjwxc-seeds.jsonl")
    summary = {
        "qidian_seed_count": qn,
        "jjwxc_seed_count": jn,
        "harvest_files": loaded,
        "scope": "bibliographic seed IDs only; no novel prose",
    }
    (out / "seed_master_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
