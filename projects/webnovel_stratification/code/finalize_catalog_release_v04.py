#!/usr/bin/env python3
"""Refresh all exports and independently hash-check a self-contained release."""
import argparse,csv,hashlib,json,sqlite3
from pathlib import Path

def finalize(root):
 root=Path(root);c=sqlite3.connect(root/'data/derived/webnovel_catalog.sqlite');c.row_factory=sqlite3.Row
 c.execute("UPDATE detail_audit SET quality_note=CASE WHEN title_seen IS NULL THEN 'No recognizable work metadata: preserve response as an unresolved access observation.' WHEN chapter_rows=0 THEN 'Recognizable work metadata without parseable chapter rows; no publication dates inferred.' ELSE 'Public table tooltips explicitly label chapter publication; displayed timestamps are separately retained as updates. Not independent work-level verification.' END")
 c.execute('''CREATE VIEW IF NOT EXISTS bibliography_dates AS
 SELECT w.work_key,w.platform,w.platform_work_id,w.title,w.author,w.genre_raw,w.status_raw,w.word_count,
 d.catalog_pub_date,d.catalog_pub_year,d.first_chapter_publication_date,d.last_chapter_publication_date,
 d.main_story_end_candidate,d.all_text_end_candidate,d.other_ending_candidate,d.ending_date_basis,
 d.external_start_year_candidate,d.last_update_date_observed,d.catalog_vs_chapter_pub_year_conflict,w.work_url
 FROM work_master w JOIN work_dates d USING(work_key)''')
 c.commit()
 integrity=c.execute('pragma integrity_check').fetchone()[0];fk=c.execute('pragma foreign_key_check').fetchall()
 assert integrity=='ok' and not fk
 names=[r[0] for r in c.execute("select name from sqlite_master where type in ('table','view') and name not like 'sqlite_%'")]
 counts={}
 for name in names:
  q=c.execute('select * from "'+name+'"');fields=[d[0] for d in q.description]
  n=0
  with (root/'data/derived'/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
   writer=csv.writer(f);writer.writerow(fields)
   for r in q:writer.writerow(r);n+=1
  counts[name]=n
 sources=[]
 for s in c.execute('select source_id,local_file,sha256 from sources'):
  p=root/s['local_file'];ok=p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256']
  sources.append(dict(source_id=s['source_id'],file=s['local_file'],hash_verified=ok))
 assert all(s['hash_verified'] for s in sources),'A source file is missing or changed'
 (root/'audit/schema_v04.sql').write_text('\n\n'.join(r[0]+';' for r in c.execute("select sql from sqlite_master where sql is not null")),encoding='utf-8')
 audit=dict(sqlite_integrity=integrity,foreign_keys_ok=not fk,all_sources_verified=len(sources),sources=sources,export_counts=counts)
 (root/'audit/release_verification_v04.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
 c.close();print(json.dumps({k:v for k,v in audit.items() if k!='sources'},indent=2))

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('root',type=Path);args=ap.parse_args();finalize(args.root)
