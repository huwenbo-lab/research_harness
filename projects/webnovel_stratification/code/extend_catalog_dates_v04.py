#!/usr/bin/env python3
"""Extend a COPY of v0.3 with catalog observations and explicitly typed dates.
Run: python extend_catalog_dates_v04.py --baseline DIR --new DIR --out NEW_DIR
"""
from __future__ import annotations
import argparse, ast, collections, csv, hashlib, json, re, shutil, sqlite3
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote
import unicodedata
from extend_database_v03 import Builder as OldBuilder, h, clean, jd
from date_parser_v04 import date_value,end_role,parse_jj_detail

SCHEMA='''
CREATE TABLE IF NOT EXISTS date_candidate (
 candidate_id TEXT PRIMARY KEY,work_key TEXT NOT NULL REFERENCES work_master(work_key),
 source_id TEXT NOT NULL REFERENCES sources(source_id),row_locator TEXT,date_value TEXT,
 date_role TEXT NOT NULL,evidence_text TEXT,confidence TEXT NOT NULL,
 is_verified INTEGER NOT NULL DEFAULT 0 CHECK(is_verified=0));
CREATE TABLE IF NOT EXISTS detail_audit (
 source_id TEXT PRIMARY KEY REFERENCES sources(source_id),work_key TEXT NOT NULL REFERENCES work_master(work_key),
 title_seen TEXT,author_seen TEXT,status_seen TEXT,chapter_rows INTEGER,metadata_json TEXT,quality_note TEXT);
CREATE TABLE IF NOT EXISTS external_bibliography (
 external_key TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),row_locator TEXT,
 source_platform TEXT,original_language TEXT,title TEXT,associated_names TEXT,authors TEXT,publishers TEXT,
 start_year_reported INTEGER,completion_status_reported TEXT,source_url TEXT,
 linked_work_key TEXT REFERENCES work_master(work_key),link_method TEXT NOT NULL,raw_record_json TEXT);
CREATE TABLE IF NOT EXISTS work_dates (
 work_key TEXT PRIMARY KEY REFERENCES work_master(work_key),
 catalog_pub_date TEXT,catalog_pub_year INTEGER,external_start_year_candidate INTEGER,
 completion_status_observed TEXT,first_chapter_publication_date TEXT,last_chapter_publication_date TEXT,latest_chapter_publication_date TEXT,
 first_chapter_update_date TEXT,earliest_chapter_update_date TEXT,
 latest_chapter_update_date TEXT,last_update_date_observed TEXT,main_story_end_candidate TEXT,all_text_end_candidate TEXT,
 other_ending_candidate TEXT,ending_date_basis TEXT,explicit_completion_date_reported TEXT,
 first_pub_date_verified TEXT,completion_date_verified TEXT,
 chapter_time_conflict INTEGER NOT NULL DEFAULT 0,catalog_vs_chapter_pub_year_conflict INTEGER NOT NULL DEFAULT 0,notes TEXT);
CREATE INDEX IF NOT EXISTS date_candidate_work_role ON date_candidate(work_key,date_role);
CREATE INDEX IF NOT EXISTS external_bibliography_work ON external_bibliography(linked_work_key);
CREATE INDEX IF NOT EXISTS detail_audit_work ON detail_audit(work_key);
'''

class Builder(OldBuilder):
 def __init__(self,baseline,new,out):
  self.base=Path(baseline);self.new=Path(new);self.out=Path(out)
  if self.out.exists():raise FileExistsError('Use a new output directory')
  shutil.copytree(self.base,self.out)
  self.c=sqlite3.connect(self.out/'data/derived/webnovel_catalog.sqlite');self.c.row_factory=sqlite3.Row
  self.c.execute('PRAGMA foreign_keys=ON');self.c.executescript(SCHEMA)
  self.initial=dict(self.c.execute('SELECT platform,count(*) FROM work_master GROUP BY platform'))
  self.logs={};self.verified=[];self.events=[];self.parsed_details=[]
  for group in self.new.iterdir():
   if group.is_dir() and (group/'retrieval_log.json').exists():
    self.logs[group.name]=json.loads((group/'retrieval_log.json').read_text())
    for p in group.glob('*manifest.json'):shutil.copy2(p,self.out/'audit'/('v04_'+group.name+'_'+p.name))
    for p in group.glob('*audit.json'):shutil.copy2(p,self.out/'audit'/('v04_'+group.name+'_'+p.name))
    shutil.copy2(group/'retrieval_log.json',self.out/'audit'/('v04_'+group.name+'_retrieval_log.json'))
    for r in self.logs[group.name]:
     self.c.execute('INSERT INTO retrieval_log(source_url,retrieved_at,status,error,local_file,bytes,sha256) VALUES(?,?,?,?,?,?,?)',
      (r.get('url'),r.get('retrieved_at'),str(r.get('status')),r.get('error'),f"v04/{group.name}/{r.get('file','')}",r.get('bytes'),r.get('sha256')))

 def source(self,path,kind,tier='direct_observation',snapshot=None):
  path=Path(path);grp=path.parent.name
  records=[r for r in self.logs.get(grp,[]) if r.get('file')==path.name and r.get('status')==200 and not r.get('error')]
  if not records:raise ValueError('No valid provenance: '+str(path))
  r=records[-1];digest=hashlib.sha256(path.read_bytes()).hexdigest()
  if digest!=r['sha256']:raise ValueError('Checksum failed')
  sid=h('v04',r['url'],digest);rel=f'data/raw/v04/{grp}/{path.name}';dest=self.out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():shutil.copy2(path,dest)
  self.c.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?,?)',
   (sid,r['url'],rel,digest,kind,r['retrieved_at'],snapshot,'Source metadata for research; underlying rights retained. No blanket republication permission inferred.',tier))
  if not any(a['source_id']==sid for a in self.verified):self.verified.append(dict(source_id=sid,local_file=rel,sha256=digest,url=r['url']))
  return sid,r

 def candidate(self,key,sid,locator,value,role,evidence,confidence):
  if value is None:return
  self.c.execute('INSERT OR IGNORE INTO date_candidate VALUES(?,?,?,?,?,?,?,?,0)',
   (h(key,sid,locator,role,value),key,sid,locator,value,role,evidence,confidence))

 def catalog(self):
  count=0;keys=set();sources={}
  for path in self.new.glob('*/catalog_observations.jsonl'):
   for line in path.read_text().splitlines():
    r=json.loads(line);p=path.parent/r['raw_file']
    if p not in sources:sources[p]=self.source(p,'official_catalog_latest_publication')
    sid,rec=sources[p]
    if r['declared_pub_year']!=r['requested_year']:raise ValueError('Mismatched year')
    key,oid=self.observe(sid,'row:'+str(r['row_on_page']),r,rec,'platform_catalog_publication',r['declared_pub_year'],r['date_raw'],'official_catalog_id_observed')
    self.c.execute('INSERT OR IGNORE INTO catalog_membership VALUES(?,?,?,?,?,?,0)',
     (oid,'jjwxc',r['requested_year'],r['page'],'latest_publication','Observed next-page links, public pages <=10; not full catalog or random sample.'))
    keys.add(key);count+=1
  self.events.append(dict(source='jjwxc_catalog_v04',rows=count,unique_works=len(keys)))

 def details(self):
  for manifest in self.new.glob('*/detail_manifest.json'):
   for entry in {r['work_key']:r for r in json.loads(manifest.read_text())}.values():
    p=manifest.parent/entry['file']
    if not entry['acquired'] or not p.exists():continue
    sid,rec=self.source(p,'official_work_detail_and_chapter_metadata')
    key=entry['work_key'];wid=key.split(':')[1]
    parsed=parse_jj_detail(p.read_bytes(),wid,entry['url']);self.parsed_details.append(dict(work_key=key,**parsed))
    self.c.execute('INSERT OR REPLACE INTO detail_audit VALUES(?,?,?,?,?,?,?,?)',
     (sid,key,parsed['title'],parsed['author'],parsed['status'],len(parsed['chapters']),jd(parsed['metadata_fields']),'Live metadata extraction; chapter timestamps are update dates, not verified first publication.'))
    r=dict(platform='jjwxc',work_id=wid,title=parsed['title'],author=parsed['author'],status=parsed['status'],work_url=entry['url'])
    self.observe(sid,'work_metadata',r,rec)
    for m in parsed['date_meta']:
     role={'datepublished':'explicit_metadata_publication','datecreated':'explicit_metadata_creation',
      'datemodified':'explicit_metadata_update','og:novel:update_time':'explicit_metadata_update'}[m['field'].lower()]
     self.candidate(key,sid,'meta:'+m['field'],m['date_value'],role,m['date_raw'],'platform_reported_field')
    for ch in parsed['chapters']:
     self.c.execute('INSERT OR IGNORE INTO chapter_metadata VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)',
      (h(sid,'chapter_ordinal',ch['chapter_number_raw']),sid,key,ch['chapter_id'],ch['chapter_number_raw'],ch['chapter_title'],ch['chapter_url'],ch['word_count_raw'],ch.get('publish_time_as_supplied'),ch['update_time_as_supplied'],ch.get('is_vip_as_supplied'),None,ch['date_semantics']))
     if ch.get('publication_evidence_raw'):
      self.candidate(key,sid,'chapter_ordinal:'+ch['chapter_number_raw'],ch.get('publish_time_as_supplied'),'chapter_publication_tooltip',ch['publication_evidence_raw'],'official_explicit_label')
  (self.out/'audit/v04_detail_extraction.json').write_text(jd(self.parsed_details),encoding='utf-8')

 def tracker_metadata(self):
  paths=list(self.new.glob('*/dylan-byte-max__novel-tracker__data__jjwxc__*.json'))+list(self.new.glob('*/qidian_collection.json'))+list(self.new.glob('*/qidian_latest.json'))
  for p in paths:
   obj=json.loads(p.read_text());platform=obj.get('platform')
   if platform not in ('jjwxc','qidian') or not isinstance(obj.get('books'),list):continue
   sid,rec=self.source(p,'third_party_metadata_snapshot','third_party_snapshot',obj.get('update_time'))
   accepted=0;invalid=0
   for i,b in enumerate(obj['books'],1):
    wid=str(b.get('book_id',''));url=b.get('book_url','')
    if platform=='jjwxc':match=parse_qs(urlparse(url).query).get('novelid')==[wid] and urlparse(url).hostname=='www.jjwxc.net'
    else:match=bool(re.fullmatch(r'/book/'+re.escape(wid)+r'/?',urlparse(url).path)) and urlparse(url).hostname=='www.qidian.com'
    if not wid.isdigit() or not match or not b.get('book_name'):
     invalid+=1;continue
    genre='-'.join(str(b.get(k) or '') for k in ('nature','genre','era','theme')).strip('-') if platform=='jjwxc' else b.get('primary_tag')
    au=b.get('author_url','');aid=parse_qs(urlparse(au).query).get('authorid',[None])[0]
    r=dict(platform=platform,work_id=wid,title=b.get('book_name'),author=b.get('author'),author_id=aid,genre=genre,status=b.get('status'),word_count=b.get('word_count'),synopsis=b.get('abstract'),tags=b.get('all_tags'),work_url=url)
    key,oid=self.observe(sid,'books:'+str(i),r,rec,'external_snapshot_metadata',None,None,'third_party_id_reported')
    if date_value(b.get('publish_time')):self.candidate(key,sid,'books:'+str(i),date_value(b['publish_time']),'external_publication_date',b['publish_time'],'third_party_field_not_independently_verified')
    if date_value(b.get('update_time')):self.candidate(key,sid,'books:'+str(i),date_value(b['update_time']),'metadata_last_update',b['update_time'],'third_party_metadata_update')
    accepted+=1
   self.events.append(dict(source=p.name,rows=accepted,invalid_rows=invalid,note='Current cumulative-score or ranking snapshot used only for metadata supplementation, not historical representative sample.'))

 def external_data(self):
  paths=list(self.new.glob('*/shaido987__novel-dataset__novels_0.1.5.json'))
  if not paths:paths=list(self.new.glob('*/shaido987__novel-dataset__novels_0.1.5.csv'))
  if not paths:return
  p=paths[0];sid,rec=self.source(p,'external_translated_novel_bibliography','third_party_snapshot')
  if p.suffix=='.csv':
   csv.field_size_limit(10*1024*1024)
   with p.open(encoding='utf-8-sig',newline='') as fp:rows=list(csv.DictReader(fp))
  else:rows=json.loads(p.read_text())
  if isinstance(rows,dict):
   rows=list(rows.values()) if all(isinstance(v,dict) for v in rows.values()) else rows.get('novels',rows.get('data',[]))
  def norm(x):return ''.join(ch for ch in unicodedata.normalize('NFKC',str(x or '')).casefold() if ch.isalnum())
  title_index=collections.defaultdict(list)
  for w in self.c.execute('SELECT work_key,title,author,platform FROM work_master'):
   if w['title']:title_index[norm(w['title'])].append(dict(w))
  eng=collections.defaultdict(set)
  cw=self.c.execute('SELECT qidian_id,webnovel_url FROM crosswalk WHERE qidian_id IS NOT NULL').fetchall()
  cn=collections.Counter(r['qidian_id'] for r in cw)
  for r in cw:
   if cn[r['qidian_id']]!=1:continue
   slug=unquote((r['webnovel_url'] or '').split('/book/')[-1].rsplit('_',1)[0]);eng[norm(slug)].add('qidian:'+str(r['qidian_id']))
  stats=collections.Counter()
  for i,r in enumerate(rows,1):
   if not isinstance(r,dict) or str(r.get('original_language','')).lower()!='chinese':continue
   names=r.get('assoc_names') or [];authors=r.get('authors') or []
   def parsed_list(value):
    if not isinstance(value,str):return value
    if value.strip().startswith('['):
     try:
      result=ast.literal_eval(value)
      if isinstance(result,list):return result
     except (ValueError,SyntaxError):pass
    return [value]
   names=parsed_list(names);authors=parsed_list(authors)
   pub=str(r.get('original_publisher') or '')
   platform='jjwxc' if re.search('jjwxc|jinjiang|晋江',pub,re.I) else ('qidian' if re.search('qidian|起点',pub,re.I) else None)
   chinese=[n for n in names if re.search('[\u4e00-\u9fff]',n)]
   possible={w['work_key']:w for n in chinese for w in title_index.get(norm(n),[]) if platform is None or w['platform']==platform}
   linked=None;how='not_matched'
   if len(possible)==1:
    key,w=next(iter(possible.items()))
    if any(norm(w['author'])==norm(a) for a in authors if a and w['author']):linked=key;how='exact_title_author'
    elif key in eng.get(norm(r.get('name')),set()):linked=key;how='dual_title_academic_crosswalk'
    else:linked=key;how='unique_title_only_candidate'
   elif len(possible)>1:how='ambiguous_title'
   yr=r.get('start_year');yr=int(yr) if re.fullmatch(r'(?:19|20)\d{2}',str(yr or '')) else None
   eid='novelupdates:'+str(r.get('id',i));url='https://www.novelupdates.com/?p='+str(r.get('id',i))
   self.c.execute('INSERT OR IGNORE INTO external_bibliography VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
    (eid,sid,str(i),platform,'chinese',r.get('name'),jd(names),jd(authors),pub,yr,str(r.get('complete_original')),url,linked,how,jd(r)))
   stats[how]+=1
   if linked and yr:
    self.candidate(linked,sid,'external:'+eid,str(yr),'external_start_year',str(r.get('name'))+' | '+pub,'external_reported_year_'+how)
  self.events.append(dict(source='novelupdates_chinese_metadata',rows=sum(stats.values()),link_counts=dict(stats),note='Translated-work selection. External IDs are not Qidian/JJWXC IDs. No external-only record added to work_master.'))

 def chapter_dates(self):
  rows=self.c.execute("""SELECT c.*,s.retrieved_at,s.source_kind FROM chapter_metadata c JOIN sources s USING(source_id)
   ORDER BY c.work_key,c.chapter_id,CASE WHEN c.date_semantics LIKE 'official_%' THEN 1 ELSE 0 END,s.retrieved_at""").fetchall()
  selected={}
  for r in rows:
   seq=str(r['chapter_number_raw'] or '').strip()
   token='ordinal:'+seq if seq.isdigit() else 'row:'+r['metadata_id']
   selected[(r['work_key'],token)]=dict(r)
  books=collections.defaultdict(list)
  for r in selected.values():books[r['work_key']].append(r)
  for key,ch in books.items():
   numeric=[(int(r['chapter_number_raw']),r) for r in ch if str(r['chapter_number_raw'] or '').isdigit()]
   if not numeric:continue
   last_id=max(i for i,_ in numeric)
   for i,r in numeric:
    dt=date_value(r['update_time_as_supplied'] or r['publish_time_as_supplied'])
    pub=date_value(r['publish_time_as_supplied']) if r['date_semantics']=='official_explicit_chapter_publication_and_update' else None
    confidence='official_chapter_update' if r['date_semantics'].startswith('official_') else 'third_party_chapter_update'
    self.candidate(key,r['source_id'],'chapter_ordinal:'+str(i),dt,'chapter_update',r['chapter_title'],confidence)
    if i==1:self.candidate(key,r['source_id'],'chapter_ordinal:1',dt,'first_chapter_update',r['chapter_title'],confidence)
    if pub:
     self.candidate(key,r['source_id'],'chapter_ordinal:'+str(i),pub,'chapter_publication',r['chapter_title'],'official_explicit_label')
     if i==1:self.candidate(key,r['source_id'],'chapter_ordinal:1',pub,'first_chapter_publication',r['chapter_title'],'official_explicit_label')
     if i==last_id:self.candidate(key,r['source_id'],'chapter_ordinal:'+str(i),pub,'last_chapter_publication',r['chapter_title'],'official_explicit_label')
    role=end_role(r['chapter_title'])
    if role and i>=last_id*0.60:
     if pub:self.candidate(key,r['source_id'],'chapter_ordinal:'+str(i),pub,role.replace('_update','_publication'),r['chapter_title'],'official_explicit_label_ending_title_candidate')
     else:self.candidate(key,r['source_id'],'chapter_ordinal:'+str(i),dt,role,r['chapter_title'],confidence+'_ending_title_candidate')

 def inherited_update_metadata(self):
  for src in self.c.execute("SELECT * FROM sources WHERE source_kind='existing_bibliographic_database'").fetchall():
   p=self.out/src['local_file']
   if not p.exists() or p.suffix!='.db':continue
   if not ('chongchong12138' in p.name or '123miaomiao' in p.name):continue
   db=sqlite3.connect('file:'+str(p)+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
   if 'chongchong12138' in p.name:
    for r in db.execute('SELECT novelid,last_update FROM books'):
     key='jjwxc:'+str(r['novelid'])
     if self.c.execute('SELECT 1 FROM work_master WHERE work_key=?',(key,)).fetchone():
      self.candidate(key,src['source_id'],'books:'+str(r['novelid']),date_value(r['last_update']),'metadata_last_update',r['last_update'],'third_party_metadata_update')
   else:
    for r in db.execute('SELECT id,lastupdate,booklink FROM book100'):
     m=re.search(r'/info/(\d+)',r['booklink'] or '')
     if not m:continue
     key='qidian:'+m[1]
     if self.c.execute('SELECT 1 FROM work_master WHERE work_key=?',(key,)).fetchone():
      self.candidate(key,src['source_id'],'book100:'+str(r['id']),date_value(r['lastupdate']),'metadata_last_update',r['lastupdate'],'third_party_metadata_update')
   db.close()

 def build_dates(self):
  self.c.execute('DELETE FROM work_dates')
  for w in self.c.execute('SELECT * FROM work_master').fetchall():
   key=w['work_key'];dates=collections.defaultdict(list)
   for r in self.c.execute('SELECT * FROM date_candidate WHERE work_key=?',(key,)):dates[r['date_role']].append(r['date_value'])
   get=lambda role: max(dates[role]) if dates[role] else None
   ch=dates['chapter_update'];first=get('first_chapter_update');earliest=min(ch) if ch else None
   status=w['status_raw'];live=self.c.execute('SELECT status_seen FROM detail_audit WHERE work_key=? AND status_seen IS NOT NULL ORDER BY rowid DESC LIMIT 1',(key,)).fetchone()
   if live:status=live[0]
   completed='completed' if status and str(status).strip() in ('完结','已完成','完成','完本','已完结','已完本') else ('not_completed_or_unknown' if status else 'unknown')
   conflict=int(bool(first and earliest and first>earliest))
   ext=self.c.execute("SELECT DISTINCT start_year_reported FROM external_bibliography WHERE linked_work_key=? AND link_method IN ('exact_title_author','dual_title_academic_crosswalk') AND start_year_reported IS NOT NULL",(key,)).fetchall()
   ey=ext[0][0] if len(ext)==1 else None
   fp=get('first_chapter_publication');lp=get('last_chapter_publication');xp=get('chapter_publication')
   yr_conflict=int(bool(fp and w['platform_declared_pub_year'] and int(fp[:4])!=w['platform_declared_pub_year']))
   endings=[];basis={}
   for label in ('main_story_end_marker','all_text_end_marker','ending_marker'):
    if get(label+'_publication'):
     endings.append(get(label+'_publication'));basis[label]='explicit_chapter_publication'
    else:
     endings.append(get(label+'_update'))
     if endings[-1]:basis[label]='chapter_update_candidate'
   notes='Catalog date and chapter first-publication date are different platform fields. The last current chapter is not necessarily the main-story ending. Ending-title markers need manual validation; no verified completion was inferred.'
   if conflict:notes+=' Chapter 1 was updated later than another chapter.'
   if yr_conflict:notes+=' Catalog year differs from the explicitly labelled chapter-1 publication year.'
   last_updates=ch+dates['metadata_last_update']+dates['explicit_metadata_update']
   values=(key,w['platform_declared_pub_date'],w['platform_declared_pub_year'],ey,completed,fp,lp,xp,first,earliest,max(ch) if ch else None,max(last_updates) if last_updates else None,
     *endings,jd(basis),get('explicit_metadata_completion'),None,None,conflict,yr_conflict,notes)
   self.c.execute('INSERT INTO work_dates VALUES('+','.join('?' for _ in values)+')',values)
  self.c.execute('DROP VIEW IF EXISTS catalog_with_dates')
  self.c.execute("""CREATE VIEW catalog_with_dates AS SELECT w.*,d.external_start_year_candidate,
   d.completion_status_observed,d.first_chapter_publication_date,d.last_chapter_publication_date,d.latest_chapter_publication_date,
   d.first_chapter_update_date,d.earliest_chapter_update_date,d.latest_chapter_update_date,d.last_update_date_observed,
   d.main_story_end_candidate,d.all_text_end_candidate,d.other_ending_candidate,d.ending_date_basis,d.explicit_completion_date_reported,
   d.first_pub_date_verified,d.completion_date_verified,d.chapter_time_conflict,d.catalog_vs_chapter_pub_year_conflict,d.notes AS date_notes
   FROM work_master w JOIN work_dates d USING(work_key)""")

 def finish(self):
  self.c.commit()
  counts=dict(self.c.execute('SELECT platform,count(*) FROM work_master GROUP BY platform'))
  tests=dict(sqlite_integrity=self.c.execute('PRAGMA integrity_check').fetchone()[0]=='ok',foreign_keys=not self.c.execute('PRAGMA foreign_key_check').fetchall(),
   work_count_nondecreasing=all(counts.get(k,0)>=n for k,n in self.initial.items()),
   date_summary_one_per_work=self.c.execute('SELECT count(*) FROM work_master').fetchone()[0]==self.c.execute('SELECT count(*) FROM work_dates').fetchone()[0],
   chapter_dates_not_verified=self.c.execute('SELECT count(*) FROM work_dates WHERE first_pub_date_verified IS NOT NULL OR completion_date_verified IS NOT NULL').fetchone()[0]==0,
   new_catalog_years_agree=self.c.execute("SELECT count(*) FROM catalog_membership c JOIN source_observation s USING(observation_id) WHERE c.requested_year!=s.declared_pub_year").fetchone()[0]==0)
  for s in self.verified:
   if hashlib.sha256((self.out/s['local_file']).read_bytes()).hexdigest()!=s['sha256']:raise ValueError('Hash mismatch')
  tests['new_source_hashes_valid']=True
  summary=dict(initial_counts=self.initial,final_counts=counts,new_counts={p:counts[p]-self.initial.get(p,0) for p in counts},events=self.events,
   new_sources=len(self.verified),tests=tests,date_coverage=[])
  for p in ['jjwxc','qidian']:
   r=self.c.execute('''SELECT count(*) AS works,count(catalog_pub_date) AS catalog_dates,count(external_start_year_candidate) AS external_start_years,
    count(first_chapter_publication_date) AS chapter1_publications,count(last_chapter_publication_date) AS last_chapter_publications,count(first_chapter_update_date) AS chapter1_updates,count(latest_chapter_update_date) AS latest_chapter_updates,count(last_update_date_observed) AS metadata_or_chapter_updates,
    sum(main_story_end_candidate IS NOT NULL OR all_text_end_candidate IS NOT NULL OR other_ending_candidate IS NOT NULL) AS works_with_end_markers,
    count(explicit_completion_date_reported) AS explicit_completion_dates,sum(chapter_time_conflict) AS chapter1_date_conflicts,sum(catalog_vs_chapter_pub_year_conflict) AS catalog_chapter_year_conflicts
    FROM work_dates JOIN work_master USING(work_key) WHERE platform=?''',(p,)).fetchone()
   summary['date_coverage'].append(dict(platform=p,**dict(r)))
  for name in ['work_master','work_dates','catalog_with_dates','date_candidate','date_evidence','external_bibliography','detail_audit','chapter_metadata','catalog_membership','sources','source_observation','metadata_conflict']:
   q=self.c.execute('SELECT * FROM '+name);headers=[x[0] for x in q.description]
   with (self.out/'data/derived'/f'{name}.csv').open('w',newline='',encoding='utf-8-sig') as fp:
    writer=csv.writer(fp);writer.writerow(headers);writer.writerows(q)
  (self.out/'audit/v04_source_hashes.json').write_text(jd(self.verified),encoding='utf-8')
  (self.out/'audit/build_summary_v04.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
  if not all(tests.values()):raise AssertionError(tests)
  self.c.close();return summary

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--new',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
 b=Builder(a.baseline,a.new,a.out);b.catalog();b.details();b.tracker_metadata();b.external_data();b.chapter_dates();b.inherited_update_metadata();b.build_dates();print(json.dumps(b.finish(),ensure_ascii=False,indent=2))
