#!/usr/bin/env python3
"""Offline SQLite integration. Preserve source evidence and unknown publication years.
Run from the project folder: python code/build_database.py --root .
"""
from __future__ import annotations
import argparse, ast, csv, io, hashlib, json, re, sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlparse, parse_qs

def sha(b): return hashlib.sha256(b).hexdigest()
def text(v): return '' if v is None else ' '.join(str(v).replace('\xa0',' ').split())
def platform_id(url, platform):
    u=urlparse('https:'+url if url.startswith('//') else url)
    if platform=='qidian' and (u.hostname or '').endswith('.qidian.com'):
        m=re.fullmatch(r'/(?:book|info)/(\d+)/?',u.path)
        return m.group(1) if m else None
    if platform=='jjwxc' and (u.hostname or '').endswith('.jjwxc.net'):
        s=parse_qs(u.query).get('novelid',[''])[0]
        return s if s.isdigit() else None
    return None

def unit_number(s):
    m=re.fullmatch(r'(\d+(?:\.\d+)?)(万|亿)?(?:字|周)?',text(s).replace(',',''))
    if not m:return None
    try:return int(Decimal(m.group(1))*{'万':10000,'亿':100000000,None:1}[m.group(2)])
    except (InvalidOperation,OverflowError):return None

def read_csv(path):
    for enc in ['utf-8-sig','gb18030']:
        try:return list(csv.DictReader(io.StringIO(path.read_text(encoding=enc))))
        except UnicodeDecodeError:pass
    raise ValueError(f'Unknown encoding: {path}')

SCHEMA='''
PRAGMA foreign_keys=ON;
CREATE TABLE sources (
 source_id TEXT PRIMARY KEY, source_url TEXT NOT NULL, local_file TEXT NOT NULL,
 sha256 TEXT NOT NULL, source_kind TEXT, retrieved_at TEXT, snapshot_time_raw TEXT,
 license_note TEXT NOT NULL, evidence_tier TEXT NOT NULL);
CREATE TABLE retrieval_log (
 retrieval_id INTEGER PRIMARY KEY, source_url TEXT, retrieved_at TEXT, status TEXT,
 error TEXT, local_file TEXT, bytes INTEGER, sha256 TEXT);
CREATE TABLE work_master (
 work_key TEXT PRIMARY KEY, platform TEXT NOT NULL, platform_work_id TEXT NOT NULL,
 title TEXT, author TEXT, author_id TEXT, platform_declared_pub_date TEXT,
 platform_declared_pub_year INTEGER, first_pub_year_verified INTEGER,
 date_confidence TEXT NOT NULL, genre_raw TEXT, genre TEXT, originality TEXT,
 orientation TEXT, setting TEXT, viewpoint TEXT, status_raw TEXT,
 word_count INTEGER, synopsis TEXT, tags_raw TEXT, work_url TEXT,
 preferred_observation_id TEXT, identity_status TEXT NOT NULL,
 UNIQUE(platform,platform_work_id));
CREATE TABLE source_observation (
 observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 row_locator TEXT, work_key TEXT NOT NULL REFERENCES work_master(work_key),
 title TEXT, author TEXT, author_id TEXT, date_raw TEXT, date_type TEXT NOT NULL,
 declared_pub_year INTEGER, genre_raw TEXT, status_raw TEXT, word_count INTEGER,
 observed_at TEXT, raw_record_json TEXT NOT NULL, UNIQUE(source_id,row_locator));
CREATE TABLE candidate_work (
 candidate_id TEXT PRIMARY KEY, platform TEXT NOT NULL, title TEXT NOT NULL,
 author TEXT NOT NULL, linked_work_key TEXT REFERENCES work_master(work_key),
 link_method TEXT NOT NULL, source_count INTEGER NOT NULL,
 warning TEXT NOT NULL, UNIQUE(platform,title,author));
CREATE TABLE market_visibility (
 visibility_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 candidate_id TEXT NOT NULL REFERENCES candidate_work(candidate_id),
 work_key TEXT REFERENCES work_master(work_key), snapshot_time_raw TEXT,
 snapshot_timezone TEXT, source_week_label TEXT, rank_type TEXT, rank INTEGER,
 url_as_supplied TEXT, category_as_supplied TEXT, status_as_supplied TEXT,
 intro_as_supplied TEXT, row_locator TEXT NOT NULL, UNIQUE(source_id,row_locator));
CREATE TABLE candidate_observation (
 candidate_observation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 candidate_id TEXT NOT NULL REFERENCES candidate_work(candidate_id), row_locator TEXT NOT NULL,
 date_raw TEXT, date_type TEXT NOT NULL, raw_record_json TEXT NOT NULL);
CREATE TABLE historical_recommendation (
 recommendation_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 work_key TEXT NOT NULL REFERENCES work_master(work_key), recommendation_type TEXT NOT NULL,
 period_start TEXT, period_end TEXT, source_row_id TEXT NOT NULL, raw_record_json TEXT NOT NULL);
CREATE VIEW historical_recommendation_distinct AS
 SELECT work_key,recommendation_type,period_start,period_end,COUNT(*) AS duplicated_source_rows
 FROM historical_recommendation GROUP BY 1,2,3,4;
CREATE TABLE crosswalk (
 crosswalk_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 row_locator TEXT, qidian_id TEXT, webnovel_id TEXT, qidian_url TEXT, webnovel_url TEXT,
 mapping_status TEXT NOT NULL);
CREATE TABLE text_availability (
 work_key TEXT PRIMARY KEY REFERENCES work_master(work_key),
 synopsis_acquired INTEGER NOT NULL CHECK(synopsis_acquired IN (0,1)),
 chapters_acquired INTEGER NOT NULL DEFAULT 0, full_text_acquired INTEGER NOT NULL DEFAULT 0,
 online_full_text_access TEXT NOT NULL, redistribution_permission TEXT NOT NULL);
CREATE TABLE annual_coverage (
 platform TEXT NOT NULL, requested_year INTEGER NOT NULL, declared_catalog_pages INTEGER,
 planned_pages_json TEXT, accepted_pages INTEGER, accepted_observations INTEGER,
 unique_works INTEGER, year_filter_validated INTEGER, status TEXT NOT NULL,
 coverage_population TEXT NOT NULL, PRIMARY KEY(platform,requested_year));
CREATE TABLE quarantine (
 quarantine_id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id),
 reason TEXT NOT NULL, excluded_rows INTEGER NOT NULL, evidence TEXT NOT NULL);
CREATE TABLE sociological_coding (
 coding_id TEXT PRIMARY KEY, work_key TEXT NOT NULL REFERENCES work_master(work_key),
 variable TEXT NOT NULL, value TEXT, evidence_source TEXT NOT NULL,
 evidence_location TEXT NOT NULL, coder TEXT NOT NULL, coding_version TEXT NOT NULL,
 validated INTEGER NOT NULL DEFAULT 0);
CREATE INDEX obs_work ON source_observation(work_key);
CREATE INDEX work_title_author ON work_master(platform,title,author);
CREATE INDEX old_candidate_idx ON candidate_observation(candidate_id,source_id);
CREATE INDEX work_year ON work_master(platform,platform_declared_pub_year);
CREATE INDEX candidate_link ON candidate_work(linked_work_key);
CREATE INDEX market_candidate ON market_visibility(candidate_id);
CREATE VIEW candidate_latest AS
 SELECT * FROM (SELECT m.*,ROW_NUMBER() OVER (PARTITION BY candidate_id ORDER BY snapshot_time_raw DESC,source_id,row_locator) AS snapshot_order FROM market_visibility m) WHERE snapshot_order=1;
CREATE VIEW catalog_index AS
 SELECT work_key AS record_key,platform,platform_work_id,title,author,
 platform_declared_pub_year,first_pub_year_verified,genre,status_raw,word_count,
 synopsis,work_url,identity_status FROM work_master
 UNION ALL
 SELECT c.candidate_id,c.platform,NULL,c.title,c.author,NULL,NULL,m.category_as_supplied,m.status_as_supplied,NULL,m.intro_as_supplied,NULL,
 'title_author_candidate_unresolved' FROM candidate_work c LEFT JOIN candidate_latest m ON c.candidate_id=m.candidate_id WHERE c.linked_work_key IS NULL;
CREATE VIEW publication_year_summary AS
 SELECT platform,platform_declared_pub_year AS year,COUNT(*) AS unique_works,
 SUM(CASE WHEN title IS NOT NULL AND title!='' THEN 1 ELSE 0 END) AS with_title,
 SUM(CASE WHEN synopsis IS NOT NULL AND synopsis!='' THEN 1 ELSE 0 END) AS with_synopsis
 FROM work_master GROUP BY platform,platform_declared_pub_year;
'''

class Builder:
    def __init__(self,root):
        self.root=root;self.out=root/'data/derived';self.out.mkdir(parents=True,exist_ok=True)
        self.tmp=self.out/'webnovel_catalog.building.sqlite'
        if self.tmp.exists():self.tmp.unlink()
        self.db=sqlite3.connect(self.tmp);self.db.row_factory=sqlite3.Row
        self.db.executescript(SCHEMA);self.logs={};self.source_ids={};self.priority={}
        self.qa={'source_hash_checks':[],'synthetic_exclusions':[],'year_checks':[],
                 'unhandled_metadata_files':[],'warnings':[]}
        for f in sorted((root/'data/raw').rglob('retrieval_log.json')):
            for item in json.loads(f.read_text()):
                rel=(f.parent/item['file']).relative_to(root).as_posix() if item.get('file') else None
                self.logs[rel]=item
                self.db.execute('INSERT INTO retrieval_log(source_url,retrieved_at,status,error,local_file,bytes,sha256) VALUES(?,?,?,?,?,?,?)',
                   (item.get('url'),item.get('retrieved_at',item.get('retrieved_at_utc')),str(item.get('status')),item.get('error'),rel,item.get('bytes'),item.get('sha256')))

    def source(self,f,kind,tier='source_reported',snapshot=None):
        rel=f.relative_to(self.root).as_posix()
        if rel in self.source_ids:return self.source_ids[rel]
        h=sha(f.read_bytes());log=self.logs.get(rel,{})
        expected=log.get('sha256')
        if expected and expected!=h:raise ValueError(f'Hash mismatch {rel}')
        self.qa['source_hash_checks'].append({'file':rel,'matched_retrieval_hash':bool(expected),'sha256':h})
        url=log.get('url','local:'+rel);sid=sha((url+'\0'+h).encode())
        note='Public bibliographic metadata; underlying work rights reserved; no novel full text acquired. Check source terms before republication.'
        self.db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?,?)',
            (sid,url,rel,h,kind,log.get('retrieved_at',log.get('retrieved_at_utc')),snapshot,note,tier))
        self.source_ids[rel]=sid;return sid

    def observation(self,sid,locator,r,priority=1):
        pid=str(r['work_id']);p=r['platform']
        if not re.fullmatch(r'\d+',pid):raise ValueError('Non-platform ID supplied to master')
        key=p+':'+pid;oid=sha((sid+'\0'+str(locator)).encode());dt=r.get('date_type','unresolved')
        year=r.get('declared_pub_year') if dt=='platform_catalog_publication' else None
        self.db.execute('INSERT OR IGNORE INTO work_master(work_key,platform,platform_work_id,date_confidence,identity_status) VALUES(?,?,?,?,?)',
            (key,p,pid,'unresolved','source_supplied_platform_id'))
        self.db.execute('INSERT OR IGNORE INTO source_observation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (oid,sid,str(locator),key,r.get('title'),r.get('author'),r.get('author_id'),r.get('date_raw'),dt,year,
             r.get('genre_raw'),r.get('status'),r.get('word_count'),r.get('observed_at'),json.dumps(r,ensure_ascii=False)))
        if priority>=self.priority.get(key,-1):
            self.priority[key]=priority
            self.db.execute('''UPDATE work_master SET title=?,author=?,author_id=?,
                platform_declared_pub_date=?,platform_declared_pub_year=?,first_pub_year_verified=NULL,
                date_confidence=?,genre_raw=?,genre=?,originality=?,orientation=?,setting=?,viewpoint=?,
                status_raw=?,word_count=?,synopsis=?,tags_raw=?,work_url=?,preferred_observation_id=?,identity_status=? WHERE work_key=?''',
               (r.get('title'),r.get('author'),r.get('author_id'),r.get('date_raw') if year else None,year,
                'platform_label_not_independently_verified' if year else 'unresolved',r.get('genre_raw'),r.get('genre'),
                r.get('originality'),r.get('orientation'),r.get('setting'),r.get('viewpoint'),r.get('status'),r.get('word_count'),
                r.get('synopsis'),r.get('tags_raw'),r.get('work_url'),oid,
                'official_catalog_id_observed' if r.get('source_kind')=='live_official_catalog' else 'source_supplied_platform_id',key))
        self.db.execute("UPDATE work_master SET title=COALESCE(NULLIF(title,''),?),author=COALESCE(NULLIF(author,''),?),author_id=COALESCE(NULLIF(author_id,''),?) WHERE work_key=?",
            (r.get('title'),r.get('author'),r.get('author_id'),key))
        return key

    def jjwxc(self):
        from collect_catalog import parse_jjwxc
        year_ids=defaultdict(set)
        for f in sorted((self.root/'data/raw/pilot').glob('jjwxc_catalog.html')):
            log=self.logs.get(f.relative_to(self.root).as_posix(),{})
            rows,_=parse_jjwxc(f.read_bytes(),log.get('url',''),log.get('retrieved_at_utc',''))
            sid=self.source(f,'official_catalog_unfiltered','direct_observation')
            for i,r in enumerate(rows,1):
                r['selection_method']='unfiltered_discovery_top_page';self.observation(sid,i,r,2)
        for f in sorted((self.root/'data/raw').rglob('jjwxc_observations.jsonl')):
            grouped=defaultdict(list)
            for line in f.read_text().splitlines():
                if line.strip():
                    r=json.loads(line);grouped[r['raw_file']].append(r)
            for raw_name,rows in grouped.items():
                raw=f.parent/raw_name;sid=self.source(raw,'official_annual_catalog_page','direct_observation')
                if sha(raw.read_bytes())!=rows[0]['raw_sha256']:raise ValueError('Annual raw hash mismatch')
                if not all(r['declared_pub_year']==r['requested_year'] for r in rows):raise ValueError('Annual filter mismatch')
                y=rows[0]['requested_year']
                for r in rows:
                    year_ids[y].add(r['work_id']);self.observation(sid,r['row_on_page'],r,3)
            audit=f.parent/'jjwxc_annual_audit.json'
            if audit.exists():
                for a in json.loads(audit.read_text()):
                    if 'page' in a:continue
                    y=a['year'];n=sum(len(rs) for rs in grouped.values() if rs[0]['requested_year']==y)
                    self.db.execute('INSERT OR REPLACE INTO annual_coverage VALUES(?,?,?,?,?,?,?,?,?,?)',
                       ('jjwxc',y,a.get('declared_pages'),json.dumps(a.get('planned_pages')),a.get('accepted_pages',0),n,len(year_ids[y]),
                        int(a.get('year_filter_validated',False)),('first_page_only_access_limited' if a.get('accepted_pages')==1 else a['status']),
                        'Currently retained official catalog; not all historically published works'))
            self.qa['year_checks'].append({'file':str(f.relative_to(self.root)),'all_accepted_rows_match_requested_year':True})
        for y in range(2005,2026):
            for p in ['jjwxc','qidian']:
                self.db.execute('INSERT OR IGNORE INTO annual_coverage VALUES(?,?,?,?,?,?,?,?,?,?)',
                    (p,y,None,None,0,0,0,0,'not_collected','Current catalogue sampling; completeness not established'))

    def golem(self):
        f=self.root/'data/raw/pilot/golem_bookList.csv'
        if not f.exists():return
        rows=read_csv(f);sid=self.source(f,'academic_id_crosswalk');counts=Counter(r.get('qidianBookId') for r in rows if r.get('qidianBookId'))
        for n,r in enumerate(rows,1):
            q=r.get('qidianBookId','');w=r.get('webnovelBookId','')
            state='missing_qidian_id' if not q else ('duplicate_qidian_mapping_needs_review' if counts[q]>1 else 'source_supplied_unverified_mapping')
            self.db.execute('INSERT INTO crosswalk VALUES(?,?,?,?,?,?,?,?)',(sha((sid+str(n)).encode()),sid,str(n),q or None,w or None,r.get('qidianUrl'),r.get('webnovelUrl'),state))
            if q:self.observation(sid,n,dict(platform='qidian',work_id=q,title=None,author=None,date_type='unresolved',work_url=r['qidianUrl'],mapping_status=state),0)

    def existing_databases(self):
        base=self.root/'data/raw/metadata';seen=set()
        for f in sorted(base.glob('*.db')):
            h=sha(f.read_bytes())
            if h in seen:
                self.qa['warnings'].append({'file':f.name,'reason':'byte_identical_database_not_double_counted'});continue
            seen.add(h);sid=self.source(f,'existing_bibliographic_database')
            c=sqlite3.connect(f'file:{f}?mode=ro',uri=True);c.row_factory=sqlite3.Row;c.execute('PRAGMA trusted_schema=OFF')
            tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'rankbook' in tables:
                sql='SELECT b.id source_row_id,b.book_id,b.bookName,b.authorName,b.channelName,r.type,r.fromDate,r.toDate FROM rankbook b JOIN rank r ON b.rank_id=r.id'
                for row in c.execute(sql):
                    d=dict(row);pid=text(d['book_id'])
                    if not pid.isdigit():continue
                    r=dict(platform='qidian',work_id=pid,title=d['bookName'],author=d['authorName'],genre_raw=d['channelName'],genre=d['channelName'],date_type='recommendation_period_not_publication',date_raw=d['fromDate']+' / '+d['toDate'],work_url=f'https://www.qidian.com/book/{pid}/',source_original=d)
                    locator='rankbook:'+str(d['source_row_id']);key=self.observation(sid,locator,r,-1)
                    self.db.execute('INSERT INTO historical_recommendation VALUES(?,?,?,?,?,?,?,?)',
                      (sha((sid+locator).encode()),sid,key,{1:'strong_recommendation',2:'sanjiang_recommendation'}.get(d['type'],'unknown'),d['fromDate'].replace('.','-'),d['toDate'].replace('.','-'),str(d['source_row_id']),json.dumps(d,ensure_ascii=False)))
            for table in sorted(tables & {'book100','viprank','freerank','books'}):
                if table=='books' and 'chongchong' not in f.name:continue
                for n,row in enumerate(c.execute('SELECT * FROM "'+table+'"'),1):
                    d=dict(row);p='qidian' if table=='book100' else 'jjwxc'
                    url=d.get('booklink',d.get('book_url',d.get('url','')));pid=platform_id(url,p)
                    if not pid:
                        self.qa['warnings'].append({'file':f.name,'row':n,'reason':'invalid_book_url'});continue
                    if table=='book100':
                        r=dict(title=d['bookname'],author=d['bookwriter'],genre_raw=d['booktype'],genre=d['booktype'],synopsis=d['bookinfo'],date_raw=d['lastupdate'],date_type='last_update_not_publication')
                    elif table in ('viprank','freerank'):
                        txt=d.get('recommend_reason','') or '';aid=parse_qs(urlparse(d.get('author_url','')).query).get('authorid',[None])[0]
                        r=dict(title=d['book_name'],author=d['author_name'],author_id=aid,genre_raw=d.get('category'),genre=d.get('category'),tags_raw=d.get('tag'),status=d.get('state'),word_count=d.get('word_count'),
                          synopsis=txt if txt.lstrip().startswith('文案') else None,date_type='unresolved',source_text_type='synopsis' if txt.lstrip().startswith('文案') else 'unclassified_recommendation_text')
                    else:
                        r=dict(title=d['title'],author=d['author'],author_id=d.get('authorid'),genre_raw=d.get('category'),genre=d.get('category'),tags_raw=d.get('tags'),status=d.get('completion'),word_count=d.get('word_count'),synopsis=d.get('abstract'),date_raw=d.get('last_update'),date_type='last_update_not_publication',observed_at=d.get('crawled_at'),selection_note='Personalized baihe selection; AI score and AI analysis tables excluded')
                    r.update(platform=p,work_id=pid,work_url=url,source_original=d)
                    self.observation(sid,table+':'+str(n),r,1)
            c.close()
        for f in sorted(base.glob('sanliyang*csv')):
            if f.name.endswith('detail.csv'):continue
            sid=self.source(f,'existing_bibliographic_csv')
            for n,d in enumerate(read_csv(f),1):
                pid=platform_id(d.get('book_url',''),'qidian')
                if not pid:continue
                tag=d.get('tags','')
                try:tags=ast.literal_eval(tag) if tag.startswith('[') else tag.split(',')
                except (ValueError,SyntaxError):tags=[]
                self.observation(sid,n,dict(platform='qidian',work_id=pid,title=d.get('book_name'),author=d.get('author'),genre_raw=tag,genre=tags[0] if tags else None,synopsis=d.get('summary'),work_url=d['book_url'],date_type='unresolved',source_original=d),1)

    def academic_meta(self):
        for f in sorted((self.root/'data/raw').rglob('*qidianMeta.csv')):
            sid=self.source(f,'academic_work_metadata')
            for n,row in enumerate(read_csv(f),1):
                pid=row.get('qidianId','')
                if not pid.isdigit():continue
                m=re.search(r'/author/(\d+)',row.get('qd_author_link',''))
                r=dict(platform='qidian',work_id=pid,title=row.get('qd_title'),author=row.get('qd_author'),
                  author_id=m.group(1) if m else None,date_raw=row.get('qd_novel_update_time'),date_type='last_update_not_publication',
                  genre_raw=row.get('qd_genre','')+'-'+row.get('qd_category',''),genre=row.get('qd_genre'),
                  word_count=unit_number(row.get('qd_numberOfWords','')),synopsis=row.get('qd_description'),
                  work_url=f'https://www.qidian.com/book/{pid}/',source_original=row)
                self.observation(sid,n,r,2)

    def qidian_snapshots(self):
        candidates={};market=[]
        for f in sorted((self.root/'data/raw/pilot').glob('qidian_2026_W*.json')):
            obj=json.loads(f.read_text());books=obj['books'];snap=obj.get('scraped_at');week=obj.get('week')
            synthetic=bool(books) and all(str(r.get('intro','')).startswith('这是一部关于') for r in books)
            sid=self.source(f,'third_party_ranking_snapshot','synthetic_excluded' if synthetic else 'third_party_not_independently_validated',snap)
            if synthetic:
                ev='All intros match the repository test generator; week-formatted timestamp and synthetic numeric IDs. See scraper/generate_sample.py.'
                self.db.execute('INSERT INTO quarantine VALUES(?,?,?,?,?)',(sha((sid+'synthetic').encode()),sid,'synthetic_frontend_test_data',len(books),ev))
                self.qa['synthetic_exclusions'].append({'file':f.name,'excluded_rows':len(books)});continue
            for n,b in enumerate(books,1):
                t=text(b.get('title'));a=text(b.get('author'))
                if not t or not a:continue
                cid='candidate:qidian:'+sha((t+'\0'+a).encode())[:24]
                c=candidates.setdefault(cid,{'title':t,'author':a,'sources':set()});c['sources'].add(sid)
                market.append((sha((sid+'\0'+str(n)).encode()),sid,cid,None,snap,'unspecified',week,b.get('rank_type'),b.get('rank'),b.get('url'),b.get('category'),b.get('status'),b.get('intro'),str(n)))
        for cid,c in candidates.items():
            matches=self.db.execute('SELECT work_key FROM work_master WHERE platform=? AND title=? AND author=?',('qidian',c['title'],c['author'])).fetchall()
            link=matches[0][0] if len(matches)==1 else None
            self.db.execute('INSERT INTO candidate_work VALUES(?,?,?,?,?,?,?,?)',
                (cid,'qidian',c['title'],c['author'],link,'unique_exact_title_author_to_academic_metadata' if link else 'unresolved_no_valid_platform_id',len(c['sources']),
                 'Category URLs are not work IDs; these are 2026 snapshots, not publication cohorts'))
        for rec in market:
            vals=list(rec);vals[3]=self.db.execute('SELECT linked_work_key FROM candidate_work WHERE candidate_id=?',(vals[2],)).fetchone()[0]
            self.db.execute('INSERT INTO market_visibility VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',vals)

    def unlinked_old_csv(self):
        f=self.root/'data/raw/metadata/ikaixu__QiDian__out.csv'
        if not f.exists():return
        sid=self.source(f,'existing_qidian_name_author_csv')
        for n,d in enumerate(read_csv(f),1):
            t=text(d.get('小说名称'));a=text(d.get('作者'))
            if not t or not a:continue
            cid='candidate:qidian:'+sha((t+'\0'+a).encode())[:24]
            self.db.execute('INSERT OR IGNORE INTO candidate_work VALUES(?,?,?,?,?,?,?,?)',(cid,'qidian',t,a,None,'unresolved_no_valid_platform_id',1,'Original CSV has no platform ID; 更新时间 is not publication'))
            self.db.execute('INSERT INTO candidate_observation VALUES(?,?,?,?,?,?,?)',(sha((sid+str(n)).encode()),sid,cid,str(n),d.get('更新时间'),'last_update_not_publication',json.dumps(d,ensure_ascii=False)))
        for c in self.db.execute('SELECT * FROM candidate_work').fetchall():
            matches=self.db.execute('SELECT work_key FROM work_master WHERE platform=? AND title=? AND author=?',('qidian',c['title'],c['author'])).fetchall()
            if len(matches)==1:
                self.db.execute('UPDATE candidate_work SET linked_work_key=?,link_method=? WHERE candidate_id=?',(matches[0][0],'unique_exact_title_author_to_source_metadata',c['candidate_id']))
                self.db.execute('UPDATE market_visibility SET work_key=? WHERE candidate_id=?',(matches[0][0],c['candidate_id']))
        self.db.execute('UPDATE candidate_work SET source_count=(SELECT COUNT(DISTINCT source_id) FROM (SELECT source_id FROM market_visibility WHERE candidate_id=candidate_work.candidate_id UNION SELECT source_id FROM candidate_observation WHERE candidate_id=candidate_work.candidate_id))')

    def finish(self):
        self.db.execute('INSERT INTO text_availability SELECT work_key,CASE WHEN synopsis IS NOT NULL AND synopsis!="" THEN 1 ELSE 0 END,0,0,"not_checked","not_assumed" FROM work_master')
        tables=[r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts={}
        for table in tables:
            cur=self.db.execute(f'SELECT * FROM "{table}"');cols=[d[0] for d in cur.description];rows=cur.fetchall();counts[table]=len(rows)
            with (self.out/(table+'.csv')).open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(cols);w.writerows(rows)
        fk=self.db.execute('PRAGMA foreign_key_check').fetchall();ic=self.db.execute('PRAGMA integrity_check').fetchone()[0]
        if fk or ic!='ok':raise ValueError(f'Database failed checks: {fk}, {ic}')
        self.qa.update(table_rows=counts,sqlite_integrity=ic,foreign_key_violations=len(fk),
            independent_first_pub_years=self.db.execute('SELECT COUNT(*) FROM work_master WHERE first_pub_year_verified IS NOT NULL').fetchone()[0],
            publication_years=[dict(r) for r in self.db.execute('SELECT * FROM publication_year_summary ORDER BY platform,year')],
            generated_at_utc=datetime.now(timezone.utc).isoformat(timespec='seconds'))
        self.db.commit();self.db.close();self.tmp.replace(self.out/'webnovel_catalog.sqlite')
        (self.root/'reports').mkdir(exist_ok=True)
        (self.root/'reports/build_audit.json').write_text(json.dumps(self.qa,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(counts,ensure_ascii=False,indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);a=ap.parse_args()
    b=Builder(a.root);b.jjwxc();b.golem();b.existing_databases();b.academic_meta();b.qidian_snapshots();b.unlinked_old_csv();b.finish()
if __name__=='__main__':main()
