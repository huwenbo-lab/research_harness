#!/usr/bin/env python3
"""Audit catalog observations before substantive analysis."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def safe_rate(series: pd.Series) -> float:
    if len(series) == 0:
        return float("nan")
    s = series.fillna("").astype(str).str.strip()
    return float((s != "").mean())


def infer_year(df: pd.DataFrame) -> pd.Series:
    if "date_raw" not in df.columns:
        return pd.Series(pd.NA, index=df.index, dtype="Int64")
    years = pd.to_numeric(
        df["date_raw"].fillna("").astype(str).str.extract(r"((?:19|20)\d{2})", expand=False),
        errors="coerce",
    )
    return years.astype("Int64")


def audit(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = ["platform", "work_id", "title_observed", "date_raw"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df.copy()
    df["inferred_year"] = infer_year(df)
    if "author_id_observed" not in df:
        df["author_id_observed"] = ""
    if "genre_raw" not in df:
        df["genre_raw"] = ""
    if "status_raw" not in df:
        df["status_raw"] = ""
    if "work_url" not in df:
        df["work_url"] = ""

    rows = []
    group_cols = ["platform", "inferred_year"]
    for (platform, year), g in df.groupby(group_cols, dropna=False):
        ids = g["work_id"].fillna("").astype(str).str.strip()
        nonempty_ids = ids[ids != ""]
        rows.append({
            "platform": platform,
            "year": year,
            "raw_records": len(g),
            "unique_work_ids": nonempty_ids.nunique(),
            "duplicate_work_id_records": int(nonempty_ids.duplicated(keep=False).sum()),
            "work_id_available_rate": safe_rate(g["work_id"]),
            "title_available_rate": safe_rate(g["title_observed"]),
            "author_id_available_rate": safe_rate(g["author_id_observed"]),
            "date_available_rate": safe_rate(g["date_raw"]),
            "genre_available_rate": safe_rate(g["genre_raw"]),
            "status_available_rate": safe_rate(g["status_raw"]),
            "work_url_available_rate": safe_rate(g["work_url"]),
        })
    coverage = pd.DataFrame(rows).sort_values(["platform", "year"], na_position="last")

    dup = df[df["work_id"].fillna("").astype(str).str.strip() != ""].copy()
    dup = dup[dup.duplicated(["platform", "work_id"], keep=False)]
    dup = dup.sort_values(["platform", "work_id"])
    return coverage, dup


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", type=Path, help="One or more source-observation CSV files")
    ap.add_argument("--outdir", type=Path, required=True)
    args = ap.parse_args()

    frames = [pd.read_csv(path, dtype=str) for path in args.inputs]
    df = pd.concat(frames, ignore_index=True, sort=False)
    coverage, dup = audit(df)

    args.outdir.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(args.outdir / "coverage_by_year_platform.csv", index=False, encoding="utf-8-sig")
    dup.to_csv(args.outdir / "duplicate_id_report.csv", index=False, encoding="utf-8-sig")
    df.to_csv(args.outdir / "source_observation_combined.csv", index=False, encoding="utf-8-sig")

    print(coverage.to_string(index=False))
    print(f"\nobservations={len(df)} duplicates_reported={len(dup)}")


if __name__ == "__main__":
    main()
