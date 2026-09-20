#!/usr/bin/env python3
"""Incrementally maintain a ready-to-use metadata database from harvest batches.

No novel prose is ingested. Every source file is content-hashed; re-ingesting the
same batch is idempotent. Dates retain their evidence role rather than being
silently promoted to verified publication/completion dates.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS works (
  platform TEXT NOT NULL,
  work_id TEXT NOT NULL,
  title TEXT,
  author TEXT,
  status TEXT,
  genre TEXT,
  audience_channel TEXT,
  work_url TEXT,
  catalog_pub_year INTEGER,
  first_seen_at TEXT,
  last_seen_at TEXT,
  seed_sources_json TEXT,
  PRIMARY KEY(platform, work_id)
);
CREATE TABLE IF NOT EXISTS work_dates (
  platform TEXT NOT NULL,
  work_id TEXT NOT NULL,
  platform_reported_publication_date TEXT,
  publication_date_basis TEXT,
  first_chapter_publication_date TEXT,
  last_chapter_publication_date TEXT,
  last_update_date TEXT,
  completion_date_candidate TEXT,
  completion_date_basis TEXT,
  date_observed_at TEXT,
  PRIMARY KEY(platform, work_id),
  FOREIGN KEY(platform,work_id) REFERENCES works(platform,work_id)
);
CREATE TABLE IF NOT EXISTS chapters (
  platform TEXT NOT NULL,
  work_id TEXT NOT NULL,
  chapter_key TEXT NOT NULL,
  chapter_number TEXT,
  chapter_title TEXT,
  chapter_url TEXT,
  word_count TEXT,
  publication_date TEXT,
  update_date TEXT,
  is_vip INTEGER,
  source_kind TEXT,
  observed_at TEXT,
  PRIMARY KEY(platform,work_id,chapter_key),
  FOREIGN KEY(platform,work_id) REFERENCES works(platform,work_id)
);
CREATE TABLE IF NOT EXISTS ingested_sources (
  sha256 TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  rows_read INTEGER NOT NULL,
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_works_platform_year ON works(platform,catalog_pub_year);
CREATE INDEX IF NOT EXISTS idx_dates_pub ON work_dates(platform,platform_reported_publication_date);
CREATE INDEX IF NOT EXISTS idx_chapters_work ON chapters(platform,work_id);
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            h.update(chunk)
    return h.hexdigest()


def clean(v):
    if v is None:
        return None
    v=" ".join(str(v).replace("\xa0"," ").split())
    return v or None


def upsert_work(c,platform,row,observed=None):
    wid=str(row.get("platform_work_id") or row.get("work_id") or row.get("book_id") or "").strip()
    if not wid.isdigit():
        return None
    title=clean(row.get("title"))
    author=clean(row.get("author"))
    status=clean(row.get("status") or row.get("status_raw"))
    genre=clean(row.get("genre_raw") or row.get("category") or row.get("genre"))
    channel=clean(row.get("audience_channel"))
    url=clean(row.get("work_url") or row.get("url") or row.get("source_url"))
    year=row.get("declared_pub_year") or row.get("catalog_pub_year")
    try: year=int(year) if year not in (None,"") else None
    except Exception: year=None
    obs=observed or row.get("observed_at") or utcnow()
    sources=row.get("seed_sources")
    sources_json=json.dumps(sources,ensure_ascii=False) if sources else None
    c.execute("""
      INSERT INTO works(platform,work_id,title,author,status,genre,audience_channel,work_url,
                        catalog_pub_year,first_seen_at,last_seen_at,seed_sources_json)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(platform,work_id) DO UPDATE SET
        title=COALESCE(works.title,excluded.title),
        author=COALESCE(works.author,excluded.author),
        status=COALESCE(excluded.status,works.status),
        genre=COALESCE(works.genre,excluded.genre),
        audience_channel=COALESCE(works.audience_channel,excluded.audience_channel),
        work_url=COALESCE(works.work_url,excluded.work_url),
        catalog_pub_year=COALESCE(works.catalog_pub_year,excluded.catalog_pub_year),
        last_seen_at=MAX(COALESCE(works.last_seen_at,''),COALESCE(excluded.last_seen_at,'')),
        seed_sources_json=COALESCE(excluded.seed_sources_json,works.seed_sources_json)
    """,(platform,wid,title,author,status,genre,channel,url,year,obs,obs,sources_json))
    return wid


def upsert_dates(c,platform,wid,**vals):
    c.execute("INSERT OR IGNORE INTO work_dates(platform,work_id) VALUES(?,?)",(platform,wid))
    allowed={
      "platform_reported_publication_date","publication_date_basis",
      "first_chapter_publication_date","last_chapter_publication_date",
      "last_update_date","completion_date_candidate","completion_date_basis",
      "date_observed_at"
    }
    for k,v in vals.items():
        if k not in allowed or v in (None,""):
            continue
        c.execute(f"UPDATE work_dates SET {k}=? WHERE platform=? AND work_id=?",(str(v),platform,wid))


def upsert_chapter(c,platform,wid,row,observed,source_kind):
    cid=str(row.get("chapter_id") or row.get("chapter_number_raw") or row.get("chapter_number") or "").strip()
    title=clean(row.get("chapter_title"))
    url=clean(row.get("chapter_url") or row.get("url"))
    key=cid or hashlib.sha1(((title or "")+"|"+(url or "")).encode()).hexdigest()
    if not key:
        return
    c.execute("""
      INSERT INTO chapters(platform,work_id,chapter_key,chapter_number,chapter_title,chapter_url,
                           word_count,publication_date,update_date,is_vip,source_kind,observed_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
      ON CONFLICT(platform,work_id,chapter_key) DO UPDATE SET
        chapter_title=COALESCE(excluded.chapter_title,chapters.chapter_title),
        chapter_url=COALESCE(excluded.chapter_url,chapters.chapter_url),
        word_count=COALESCE(excluded.word_count,chapters.word_count),
        publication_date=COALESCE(excluded.publication_date,chapters.publication_date),
        update_date=COALESCE(excluded.update_date,chapters.update_date),
        is_vip=COALESCE(excluded.is_vip,chapters.is_vip),
        observed_at=MAX(COALESCE(chapters.observed_at,''),COALESCE(excluded.observed_at,''))
    """,(
      platform,wid,key,
      clean(row.get("chapter_number_raw") or row.get("chapter_number")),
      title,url,clean(row.get("word_count_raw") or row.get("word_count")),
      row.get("publish_time_as_supplied") or row.get("date_published"),
      row.get("update_time_as_supplied") or row.get("display_time") or row.get("date_modified"),
      row.get("is_vip_as_supplied"),source_kind,observed
    ))


def iter_jsonl(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try: yield json.loads(line)
                except json.JSONDecodeError: continue


def ingest_file(c,path):
    sha=digest(path)
    if c.execute("SELECT 1 FROM ingested_sources WHERE sha256=?",(sha,)).fetchone():
        return 0,"already_ingested"
    name=path.name
    n=0
    kind="unknown"

    if name in ("qidian-seeds.jsonl","jjwxc-seeds.jsonl"):
        platform="qidian" if name.startswith("qidian") else "jjwxc"
        kind="seed_master"
        for row in iter_jsonl(path):
            upsert_work(c,platform,row)
            n+=1

    elif name=="qidian_catalog_records.jsonl":
        kind="qidian_catalog"
        for row in iter_jsonl(path):
            upsert_work(c,"qidian",row,row.get("observed_at"))
            n+=1

    elif name in ("jjwxc_partition_records.jsonl","jjwxc_observations.jsonl","catalog_observations.jsonl"):
        kind="jjwxc_catalog"
        for row in iter_jsonl(path):
            upsert_work(c,"jjwxc",row,row.get("observed_at"))
            n+=1

    elif name=="qidian_api_metadata.jsonl":
        kind="qidian_work_detail"
        for row in iter_jsonl(path):
            obs=row.get("observed_at") or utcnow()
            info=row.get("info") or {}
            merged={
              "work_id":row.get("work_id"),"title":info.get("title") or (row.get("seed") or {}).get("title"),
              "author":info.get("author") or (row.get("seed") or {}).get("author"),
              "status":info.get("status") or (row.get("seed") or {}).get("status_raw"),
              "category":info.get("category"),"work_url":info.get("source_url") or (row.get("seed") or {}).get("work_url")
            }
            wid=upsert_work(c,"qidian",merged,obs)
            if not wid: continue
            ending=row.get("ending_chapter_date_metadata") or {}
            upsert_dates(
              c,"qidian",wid,
              platform_reported_publication_date=info.get("date_published"),
              publication_date_basis="schema.org Book datePublished" if info.get("date_published") else None,
              last_update_date=info.get("date_modified") or info.get("update_time"),
              completion_date_candidate=ending.get("date_published"),
              completion_date_basis="ending-title chapter schema.org datePublished" if ending.get("date_published") else None,
              date_observed_at=obs
            )
            n+=1

    elif name=="qidian_chapter_catalog.jsonl":
        kind="qidian_chapter_catalog"
        for row in iter_jsonl(path):
            wid=str(row.get("book_id") or "")
            if not wid.isdigit(): continue
            upsert_work(c,"qidian",{"work_id":wid})
            upsert_chapter(c,"qidian",wid,row,utcnow(),"public_mobile_catalog")
            n+=1

    elif name=="jjwxc_detail_metadata.jsonl":
        kind="jjwxc_work_detail"
        for row in iter_jsonl(path):
            obs=row.get("observed_at") or utcnow()
            wid=upsert_work(c,"jjwxc",row,obs)
            if not wid: continue
            candidates=row.get("completion_candidates") or []
            rank={"all_text_end_marker_update":3,"main_story_end_marker_update":2,"completed_status_last_visible_chapter":1}
            best=max(candidates,key=lambda x:rank.get(x.get("role"),0),default={})
            upsert_dates(
              c,"jjwxc",wid,
              first_chapter_publication_date=row.get("first_chapter_publication_date"),
              last_chapter_publication_date=row.get("last_chapter_publication_date"),
              last_update_date=row.get("last_chapter_update_date"),
              completion_date_candidate=best.get("date_candidate"),
              completion_date_basis=best.get("basis"),
              date_observed_at=obs
            )
            for ch in row.get("chapters") or []:
                upsert_chapter(c,"jjwxc",wid,ch,obs,"official_work_chapter_table")
            n+=1
    else:
        return 0,"ignored"

    c.execute("INSERT INTO ingested_sources VALUES(?,?,?,?,?)",(sha,str(path),kind,n,utcnow()))
    return n,kind


def export_csv(c,query,path):
    cur=c.execute(query)
    with Path(path).open("w",encoding="utf-8-sig",newline="") as fp:
        w=csv.writer(fp); w.writerow([x[0] for x in cur.description]); w.writerows(cur)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--existing-db")
    ap.add_argument("--seed-dir",required=True)
    ap.add_argument("--harvest-root",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()

    out=Path(args.out); out.mkdir(parents=True,exist_ok=False)
    db=out/"webnovel-latest.sqlite"
    if args.existing_db and Path(args.existing_db).exists():
        shutil.copy2(args.existing_db,db)
    c=sqlite3.connect(db); c.execute("PRAGMA foreign_keys=ON"); c.executescript(SCHEMA)

    files=[]
    for p in Path(args.seed_dir).rglob("*.jsonl"): files.append(p)
    for p in Path(args.harvest_root).rglob("*.jsonl"): files.append(p)
    results=[]
    for p in sorted(set(files)):
        n,kind=ingest_file(c,p); results.append({"file":str(p),"rows":n,"kind":kind})
    c.commit()
    integrity=c.execute("PRAGMA integrity_check").fetchone()[0]
    counts={
      "works":c.execute("SELECT count(*) FROM works").fetchone()[0],
      "qidian_works":c.execute("SELECT count(*) FROM works WHERE platform='qidian'").fetchone()[0],
      "jjwxc_works":c.execute("SELECT count(*) FROM works WHERE platform='jjwxc'").fetchone()[0],
      "works_with_publication_date":c.execute("SELECT count(*) FROM work_dates WHERE platform_reported_publication_date IS NOT NULL OR first_chapter_publication_date IS NOT NULL").fetchone()[0],
      "works_with_completion_candidate":c.execute("SELECT count(*) FROM work_dates WHERE completion_date_candidate IS NOT NULL").fetchone()[0],
      "chapters":c.execute("SELECT count(*) FROM chapters").fetchone()[0],
      "sources":c.execute("SELECT count(*) FROM ingested_sources").fetchone()[0],
    }
    export_csv(c,"SELECT * FROM works ORDER BY platform,CAST(work_id AS INTEGER)",out/"works_latest.csv")
    export_csv(c,"SELECT * FROM work_dates ORDER BY platform,CAST(work_id AS INTEGER)",out/"work_dates_latest.csv")
    c.close()
    summary={"integrity":integrity,"counts":counts,"ingestion":results,"scope":"metadata and chapter-catalog fields only; no novel prose"}
    (out/"live_database_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__":
    main()
