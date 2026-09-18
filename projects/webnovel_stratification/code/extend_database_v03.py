#!/usr/bin/env python3
"""Append audited v0.3 metadata to a COPY of v0.2; never rewrite raw inputs.

The catalogs are bounded samples, ranking snapshots are not month-end series,
and source-reported dates are not independently verified publication dates.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, json, re, shutil, sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from bs4 import BeautifulSoup

SCHEMA = '''
CREATE TABLE IF NOT EXISTS catalog_membership (
 observation_id TEXT PRIMARY KEY REFERENCES source_observation(observation_id),
 platform TEXT NOT NULL, requested_year INTEGER, page INTEGER, sort_label TEXT,
 sampling_note TEXT NOT NULL, coverage_complete INTEGER NOT NULL DEFAULT 0 CHECK(coverage_complete IN (0,1)));
CREATE TABLE IF NOT EXISTS metadata_conflict (
 conflict_id TEXT PRIMARY KEY, work_key TEXT REFERENCES work_master(work_key),
 observation_id TEXT REFERENCES source_observation(observation_id), field TEXT,
 value_retained TEXT,value_alternative TEXT);
CREATE TABLE IF NOT EXISTS date_evidence (
 evidence_id TEXT PRIMARY KEY,work_key TEXT REFERENCES work_master(work_key),
 source_id TEXT REFERENCES sources(source_id),row_locator TEXT,
 date_raw TEXT,date_role TEXT NOT NULL,year_reported INTEGER,
 independently_verified INTEGER NOT NULL DEFAULT 0 CHECK(independently_verified IN (0,1)));
CREATE TABLE IF NOT EXISTS ranking_list (
 list_id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES sources(source_id),
 platform TEXT NOT NULL,list_name TEXT NOT NULL,list_kind TEXT,
 snapshot_date TEXT,snapshot_timezone TEXT,period_start TEXT,period_end TEXT,
 date_role TEXT NOT NULL,eligibility_note TEXT,observed_depth INTEGER,
 full_list_recovered INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS ranking_entry (
 entry_id TEXT PRIMARY KEY,list_id TEXT NOT NULL REFERENCES ranking_list(list_id),
 work_key TEXT NOT NULL REFERENCES work_master(work_key),rank INTEGER,
 metric_value_raw TEXT,metric_unit TEXT,observation_id TEXT REFERENCES source_observation(observation_id),
 UNIQUE(list_id,rank));
CREATE TABLE IF NOT EXISTS editorial_issue (
 issue_key TEXT PRIMARY KEY,platform TEXT NOT NULL,series TEXT,issue_id TEXT,
 label TEXT,source_id TEXT NOT NULL REFERENCES sources(source_id),
 issue_date TEXT,date_precision TEXT,date_confidence TEXT,date_evidence TEXT,
 retrieved_at TEXT,entry_count INTEGER,period_completeness TEXT);
CREATE TABLE IF NOT EXISTS editorial_entry (
 entry_id TEXT PRIMARY KEY,issue_key TEXT NOT NULL REFERENCES editorial_issue(issue_key),
 work_key TEXT NOT NULL REFERENCES work_master(work_key),display_order INTEGER,
 recommendation_excerpt TEXT,observation_id TEXT REFERENCES source_observation(observation_id));
CREATE TABLE IF NOT EXISTS chapter_metadata (
 metadata_id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(source_id),
 work_key TEXT REFERENCES work_master(work_key),chapter_id TEXT,chapter_number_raw TEXT,
 chapter_title TEXT,chapter_url TEXT,word_count_raw TEXT,publish_time_as_supplied TEXT,
 update_time_as_supplied TEXT,is_vip_as_supplied TEXT,is_unavailable_as_supplied TEXT,
 date_semantics TEXT NOT NULL,chapter_text_imported INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS legacy_bibliography (
 legacy_id TEXT PRIMARY KEY,source_id TEXT REFERENCES sources(source_id),row_locator TEXT,
 platform TEXT,title TEXT,source_reported_year INTEGER,source_reported_month INTEGER,
 points_raw TEXT,selection_keyword TEXT,date_semantics TEXT,raw_record_json TEXT,
 platform_work_id TEXT,author TEXT,linked_work_key TEXT REFERENCES work_master(work_key),
 UNIQUE(source_id,row_locator));
CREATE TABLE IF NOT EXISTS batch_audit (
 batch_id TEXT PRIMARY KEY,layer TEXT,platform TEXT,source_label TEXT,
 rows_imported INTEGER,unique_work_ids INTEGER,date_start TEXT,date_end TEXT,
 limitations TEXT NOT NULL);
'''

def h(*args):
    return hashlib.sha256('\x1f'.join(str(x) for x in args).encode()).hexdigest()

def clean(x):
    return ' '.join(str(x if x is not None else '').split())

def integer(x):
    s=clean(x).replace(',','').rstrip('字')
    return int(s) if re.fullmatch(r'\d+',s) else None

def qid(url,key):
    return parse_qs(urlparse(url).query).get(key,[''])[0]

def jd(x):
    return json.dumps(x,ensure_ascii=False,sort_keys=True)

class Builder:
    def __init__(self,baseline,new,out):
        self.new=Path(new);self.out=Path(out)
        self.out.mkdir(parents=True,exist_ok=False)
        (self.out/'data/derived').mkdir(parents=True)
        (self.out/'data/raw/v03').mkdir(parents=True)
        (self.out/'audit').mkdir()
        self.db=self.out/'data/derived/webnovel_catalog.sqlite'
        old=sqlite3.connect(str(Path(baseline)/'data/derived/webnovel_catalog.sqlite'))
        self.c=sqlite3.connect(self.db);old.backup(self.c);old.close()
        self.c.row_factory=sqlite3.Row
        self.c.execute('PRAGMA foreign_keys=ON');self.c.executescript(SCHEMA)
        self.initial=dict(self.c.execute('SELECT platform,COUNT(*) FROM work_master GROUP BY platform').fetchall())
        self.logs={};self.verified=[];self.batch=[]
        for d in sorted(self.new.iterdir()):
            if not d.is_dir():continue
            log=d/'retrieval_log.json'
            if log.exists():
                self.logs[d.name]=json.loads(log.read_text())
                dest=self.out/'audit'/f'{d.name}_retrieval_log.json'
                shutil.copy2(log,dest)
                for r in self.logs[d.name]:
                    self.c.execute('INSERT INTO retrieval_log(source_url,retrieved_at,status,error,local_file,bytes,sha256) VALUES(?,?,?,?,?,?,?)',
                        (r.get('url'),r.get('retrieved_at'),str(r.get('status','')),r.get('error'),f"v03/{d.name}/{r.get('file','')}",r.get('bytes'),r.get('sha256')))
            for p in d.glob('*audit.json'):
                shutil.copy2(p,self.out/'audit'/f'{d.name}_{p.name}')
            for name in ('repository_sources.json','pagination_summary.json','editorial_issues.json','jjwxc_form.json'):
                p=d/name
                if p.exists():shutil.copy2(p,self.out/'audit'/f'{d.name}_{name}')

    def source(self,path,kind,tier='direct_observation',snapshot=None):
        path=Path(path);group=path.parent.name;rel=f'data/raw/v03/{group}/{path.name}'
        records=[r for r in self.logs.get(group,[]) if r.get('file')==path.name and r.get('status')==200 and not r.get('error')]
        if not records:raise ValueError(f'No successful retrieval provenance: {path}')
        rec=records[-1];digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=rec['sha256']:raise ValueError(f'Source hash mismatch: {path}')
        sid=h('v03',rec['url'],digest)
        dest=self.out/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(path,dest)
        self.c.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?,?,?,?,?,?)',
          (sid,rec['url'],rel,digest,kind,rec['retrieved_at'],snapshot,
           'Bibliographic research input; source license and underlying content rights retained. No redistribution license inferred.',tier))
        if sid not in {x['source_id'] for x in self.verified}:
            self.verified.append(dict(source_id=sid,file=rel,sha256=digest,source_url=rec['url']))
        return sid,rec

    def observe(self,sid,loc,r,rec,role='undated_bibliographic_metadata',year=None,date=None,identity='source_platform_id_observed'):
        platform=r['platform'];wid=clean(r['work_id'])
        if platform not in ('jjwxc','qidian') or not re.fullmatch(r'[1-9]\d*',wid):raise ValueError('Invalid platform ID')
        key=platform+':'+wid;oid=h(sid,loc)
        vals=dict(work_key=key,platform=platform,platform_work_id=wid,title=clean(r.get('title')) or None,
          author=clean(r.get('author')) or None,author_id=clean(r.get('author_id')) or None,
          platform_declared_pub_date=date if role=='platform_catalog_publication' else None,
          platform_declared_pub_year=year if role=='platform_catalog_publication' else None,
          first_pub_year_verified=None,date_confidence='platform_label_not_independently_verified' if role=='platform_catalog_publication' else 'unresolved',
          genre_raw=clean(r.get('genre_raw')) or None,genre=clean(r.get('genre')) or None,
          originality=clean(r.get('originality')) or None,orientation=clean(r.get('orientation')) or None,
          setting=clean(r.get('setting')) or None,viewpoint=clean(r.get('viewpoint')) or None,
          status_raw=clean(r.get('status')) or None,word_count=integer(r.get('word_count')),
          synopsis=clean(r.get('synopsis')) or None,tags_raw=clean(r.get('tags_raw')) or None,
          work_url=r.get('work_url') or (f'https://www.jjwxc.net/onebook.php?novelid={wid}' if platform=='jjwxc' else f'https://www.qidian.com/book/{wid}/'),
          preferred_observation_id=oid,identity_status=identity)
        previous=self.c.execute('SELECT * FROM work_master WHERE work_key=?',(key,)).fetchone()
        if not previous:
            self.c.execute('INSERT INTO work_master('+','.join(vals)+') VALUES('+','.join('?' for _ in vals)+')',tuple(vals.values()))
        self.c.execute('INSERT OR IGNORE INTO source_observation VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
           (oid,sid,str(loc),key,vals['title'],vals['author'],vals['author_id'],date,role,year,
            vals['genre_raw'],vals['status_raw'],vals['word_count'],rec['retrieved_at'],jd(r)))
        if previous:
            for field in ('title','author','author_id','platform_declared_pub_date','platform_declared_pub_year','genre_raw','genre','originality','orientation','setting','viewpoint','status_raw','word_count','synopsis','tags_raw'):
                val=vals[field];old=previous[field]
                if val is not None and (old is None or old==''):
                    self.c.execute('UPDATE work_master SET '+field+'=? WHERE work_key=?',(val,key))
                elif val is not None and old is not None and str(val)!=str(old):
                    self.c.execute('INSERT OR IGNORE INTO metadata_conflict VALUES(?,?,?,?,?,?)',(h(oid,field),key,oid,field,str(old),str(val)))
            if previous['platform_declared_pub_year'] is None and vals['platform_declared_pub_year'] is not None:
                self.c.execute('UPDATE work_master SET date_confidence=? WHERE work_key=?',(vals['date_confidence'],key))
        self.c.execute('INSERT OR IGNORE INTO text_availability VALUES(?,?,0,0,?,?)',(key,0,'not_checked','not_assumed'))
        if vals['synopsis']:self.c.execute('UPDATE text_availability SET synopsis_acquired=1 WHERE work_key=?',(key,))
        if date:
            self.c.execute('INSERT OR IGNORE INTO date_evidence VALUES(?,?,?,?,?,?,?,0)',(h(oid,role,date),key,sid,str(loc),date,role,year))
        return key,oid

    def catalog(self):
        batches=[('jjwxc','jjwxc_catalog_observations.jsonl'),('catalog_pagination','observations.jsonl')]
        for group,name in batches:
            p=self.new/group/name
            if not p.exists():continue
            sources={};keys=set();n=0
            for line in p.read_text().splitlines():
                r=json.loads(line);file=r['raw_file']
                if file not in sources:sources[file]=self.source(p.parent/file,'official_catalog_'+r['sort_label'])
                sid,rec=sources[file]
                if int(r['declared_pub_year'])!=int(r['requested_year']):raise ValueError('Year filter mismatch')
                key,oid=self.observe(sid,'row:'+str(r['row_on_page']),r,rec,'platform_catalog_publication',r['declared_pub_year'],r['date_raw'],'official_catalog_id_observed')
                page=r.get('requested_page',1)
                self.c.execute('INSERT OR IGNORE INTO catalog_membership VALUES(?,?,?,?,?,?,0)',(oid,'jjwxc',r['requested_year'],page,r['sort_label'],r['sampling_note']))
                n+=1;keys.add(key)
            self.batch.append(dict(batch_id=group,layer='production_sample',platform='jjwxc',source_label=group,rows_imported=n,unique_work_ids=len(keys),date_start='2005',date_end='2025',limitations='Bounded current catalog pages; source random sort has no validated inclusion probabilities; not full historical universe.'))
        p=self.new/'jjwxc/jjwxc_next_page_access_test.html'
        if p.exists():
            import sys
            sys.path.insert(0,str(Path(__file__).parent))
            from collect_catalog import parse_jjwxc
            sid,rec=self.source(p,'official_catalog_random_page2_probe')
            rows,meta=parse_jjwxc(p.read_bytes(),rec['url'],rec['retrieved_at'])
            if meta.get('current_page')==2 and rows and all(r['declared_pub_year']==2005 for r in rows):
                for i,r in enumerate(rows,1):
                    key,oid=self.observe(sid,'row:'+str(i),r,rec,'platform_catalog_publication',2005,r['date_raw'],'official_catalog_id_observed')
                    self.c.execute('INSERT OR IGNORE INTO catalog_membership VALUES(?,?,?,?,?,?,0)',(oid,'jjwxc',2005,2,'随机排序','single_observed_next_page_access_test'))

    def chapter_source(self):
        p=self.new/'repos/dev-chenxing__jjwxc-scraper__data__novels_data.json'
        if not p.exists():return
        sid,rec=self.source(p,'third_party_selected_genre_metadata','third_party_snapshot')
        records=json.loads(p.read_text());keys=set();chapter_n=0
        for i,b in enumerate(records,1):
            r=dict(platform='jjwxc',work_id=b['novel_id'],title=b['title'],author=b.get('author'),author_id=b.get('author_id'),
             genre_raw=b.get('type_text'),genre=b.get('genre'),originality=b.get('originality'),orientation=b.get('orientation'),
             setting=b.get('era'),viewpoint=b.get('perspective'),status=b.get('status'),word_count=b.get('word_count'),
             synopsis=b.get('intro'),tags_raw=jd(b.get('tags',[])),work_url=b.get('novel_url'),
             characters_as_supplied=b.get('characters'),themes_as_supplied=b.get('themes'),rank_position_as_supplied=b.get('rank_position'))
            key,oid=self.observe(sid,'book:'+str(i),r,rec);keys.add(key)
            for j,ch in enumerate(b.get('chapters',[]),1):
                url=ch.get('url','')
                self.c.execute('INSERT OR IGNORE INTO chapter_metadata VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,0)',
                  (h(sid,i,j),sid,key,qid(url,'chapterid'),str(ch.get('number','')),ch.get('title'),url,str(ch.get('word_count','')),
                   ch.get('publish_time'),ch.get('update_time'),str(ch.get('is_vip','')),str(ch.get('is_unavailable','')),
                   'third_party_chapter_time_fields_not_independent_work_first_publication_evidence'))
                chapter_n+=1
        self.batch.append(dict(batch_id='dev_metadata',layer='metadata_enrichment',platform='jjwxc',source_label='dev-chenxing/jjwxc-scraper',rows_imported=len(records),unique_work_ids=len(keys),date_start=None,date_end=None,limitations=f'Selected genre corpus; {chapter_n} chapter metadata rows, not full text; do not treat chapter time fields as verified first publication.'))

    def legacy(self):
        root=self.new/'old_repos';n=0;titles=set();ys=[]
        for p in sorted(root.glob('pwb1997*csv')):
            sid,rec=self.source(p,'legacy_keyword_filtered_bibliography','third_party_snapshot')
            keyword=p.name.split('__')[-1][:-4]
            with p.open(encoding='utf-8-sig',newline='') as f:
                for i,r in enumerate(csv.DictReader(f),1):
                    title=clean(r.get('作品'));year=integer(r.get('年'));month=integer(r.get('月'))
                    if year is not None and not 1990<=year<=2026:year=None
                    if month is not None and not 1<=month<=12:month=None
                    self.c.execute('INSERT OR IGNORE INTO legacy_bibliography VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (h(sid,i),sid,str(i),'jjwxc',title,year,month,r.get('作品积分'),keyword,
                       'year_month_extracted_from_catalog_column_7_label_not_preserved',jd(r),None,None,None))
                    n+=1;titles.add(title)
                    if year:ys.append(year)
        self.batch.append(dict(batch_id='pwb_legacy',layer='legacy_title_only',platform='jjwxc',source_label='pwb1997/JJWXC-Crawler',rows_imported=n,unique_work_ids=0,date_start=str(min(ys)) if ys else None,date_end=str(max(ys)) if ys else None,limitations=f'Keyword-selected legacy CSV; {len(titles)} distinct title strings are NOT unique works. No author or platform ID; excluded from work_master and representative trend samples.'))

    def rankings(self):
        p=self.new/'repos/dnslin__booklist__booklist.db'
        if p.exists():
            sid,rec=self.source(p,'third_party_2025_ranking_snapshot','third_party_snapshot',snapshot='2025-03-30')
            old=sqlite3.connect(f'file:{p}?mode=ro',uri=True);old.row_factory=sqlite3.Row
            keys=set();n=0
            for rt in old.execute('SELECT * FROM ranking_types WHERE site_id=2'):
                rows=old.execute('SELECT * FROM rankings WHERE site_id=2 AND ranking_type_id=? ORDER BY rank',(rt['ranking_type_id'],)).fetchall()
                if not rows:continue
                lid=h(sid,rt['ranking_type_id']);date=rows[0]['fetch_date']
                self.c.execute('INSERT OR IGNORE INTO ranking_list VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)',
                  (lid,sid,'qidian',rt['type_name'],'reader_market_snapshot',date,'source_not_specified',None,None,'source_reported_snapshot_date',
                   'Preserve source list label; 月票榜·VIP新作 is not assumed to be overall monthly list; snapshot is March 30, not certified month-end.',len(rows)))
                for b in rows:
                    b=dict(b);url=urljoin('https://www.qidian.com/',b['book_url'] or '')
                    m=re.search(r'/book/(\d+)',url)
                    if not m or m[1]!=str(b['book_id']):raise ValueError('Ranking book ID/URL disagreement')
                    r=dict(platform='qidian',work_id=str(b['book_id']),title=b['title'],author=b['author'],genre=b.get('category'),status=b.get('creation_status'),work_url=url)
                    key,oid=self.observe(sid,'ranking:'+str(b['ranking_id']),r,rec,'ranking_snapshot',None,date);keys.add(key);n+=1
                    self.c.execute('INSERT OR IGNORE INTO ranking_entry VALUES(?,?,?,?,?,?,?)',(h(lid,b['rank']),lid,key,b['rank'],str(b['indicator_value']),b['indicator_unit'],oid))
            old.close()
            self.batch.append(dict(batch_id='dnslin_rank',layer='reader_support',platform='qidian',source_label='dnslin/booklist',rows_imported=n,unique_work_ids=len(keys),date_start='2025-03-30',date_end='2025-03-30',limitations='Five partial lists, 15 entries each; includes VIP-new-work moon-vote subset; not annual/monthly historical series.'))
        p=self.new/'jjwxc/jjwxc_rank_00.html'
        if not p.exists():return
        sid,rec=self.source(p,'official_current_monthly_early_lifecycle_ranking')
        s=BeautifulSoup(p.read_bytes(),'html.parser');text=s.get_text(' ',strip=True)
        dm=re.search(r'最后生成[^\d]*(20\d{2}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})',text)
        snapshot=dm[1] if dm else rec['retrieved_at']
        lid=h(sid,'monthly');rows=[]
        for tr in s.find_all('tr'):
            cs=tr.find_all('td',recursive=False)
            if len(cs)!=8:continue
            a=cs[2].find('a',href=lambda u:u and 'novelid=' in u)
            rank=integer(cs[0].get_text())
            if a and rank:rows.append((cs,a,rank))
        self.c.execute('INSERT OR IGNORE INTO ranking_list VALUES(?,?,?,?,?,?,?,?,?,?,?,?,0)',
          (lid,sid,'jjwxc','月度排行榜','early_lifecycle_points_snapshot',snapshot,'Asia/Shanghai',None,None,'page_generation_time_not_calendar_month_end',
           'Official rule: days 11–40 since actual publication ranked by work points; not a calendar-month vote list or directly comparable with Qidian monthly tickets.',len(rows)))
        keys=set()
        for cs,a,rank in rows:
            au=cs[1].find('a',href=lambda u:u and 'authorid=' in u);url=urljoin('https://www.jjwxc.net/',a['href'])
            date=clean(cs[7].get_text());ym=re.match(r'(\d{4})-',date);year=int(ym[1]) if ym else None
            r=dict(platform='jjwxc',work_id=qid(url,'novelid'),title=a.get_text(' ',strip=True),author=au.get_text(' ',strip=True) if au else '',
              author_id=qid(au.get('href',''),'authorid') if au else '',genre_raw=cs[3].get_text(' ',strip=True),
              status=cs[4].get_text(' ',strip=True),word_count=integer(cs[5].get_text()),work_url=url,
              synopsis=BeautifulSoup(a.get('rel','') if isinstance(a.get('rel'),str) else ' '.join(a.get('rel',[])),'html.parser').get_text(' ',strip=True))
            key,oid=self.observe(sid,'rank:'+str(rank),r,rec,'platform_catalog_publication',year,date,'official_ranking_id_observed');keys.add(key)
            self.c.execute('INSERT OR IGNORE INTO ranking_entry VALUES(?,?,?,?,?,?,?)',(h(lid,rank),lid,key,rank,clean(cs[6].get_text()),'作品积分',oid))
        self.batch.append(dict(batch_id='jj_monthly',layer='reader_support',platform='jjwxc',source_label='JJWXC official monthly early-lifecycle list',rows_imported=len(rows),unique_work_ids=len(keys),date_start=snapshot,date_end=snapshot,limitations='Current snapshot only; score-ranked 11–40-day-old works, not calendar-month votes.'))

    def editorial(self):
        root=self.new/'editorial_links'
        p=root/'editorial_issues.json'
        records=json.loads(p.read_text()) if p.exists() else []
        if not any(x.get('orderstr')=='1' and x.get('issue_id')=='1' and x.get('acquired') for x in records):
            records.append(dict(orderstr='1',issue_id='1',label='试探的脚步',acquired=True,path=str(self.new/'jjwxc/jjwxc_rank_01.html')))
        n=0;keys=set();dates=[];issues=0
        for item in records:
            if not item.get('acquired'):continue
            p=Path(item['path']) if 'path' in item else root/item['file']
            if not p.exists():continue
            s=BeautifulSoup(p.read_bytes(),'html.parser');tables=[]
            for t in s.find_all('table',cellpadding='3'):
                tr=t.find('tr');cs=tr.find_all('td',recursive=False) if tr else []
                if cs and cs[0].find('a',href=lambda u:u and 'novelid=' in u):tables.append(t)
            if not tables:continue
            sid,rec=self.source(p,'official_archived_editorial_issue')
            # Only non-book editorial paragraphs can supply an issue date.
            # Page generation dates and dates within stories are excluded.
            book_cells={id(td) for t in tables for td in t.select('td.read_small')}
            outside=[td.get_text(' ',strip=True) for td in s.select('td.read_small') if id(td) not in book_cells]
            hits=[]
            for txt in outside:
                for m in re.finditer(r'(?<!\d)((?:19|20)\d{2})\s*[-/\.年]\s*(\d{1,2})\s*[-/\.月]\s*(\d{1,2})',txt):
                    try:d=datetime(int(m[1]),int(m[2]),int(m[3])).strftime('%Y-%m-%d')
                    except ValueError:continue
                    hits.append((d,txt[max(0,m.start()-70):m.end()+30]))
            distinct=sorted({x[0] for x in hits})
            date=distinct[0] if len(distinct)==1 else None
            ikey='jjwxc:editorial:'+str(item['orderstr'])+':'+str(item['issue_id'])
            ev=' | '.join(x[1] for x in hits)
            self.c.execute('INSERT OR IGNORE INTO editorial_issue VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (ikey,'jjwxc','expert_recommendation_'+str(item['orderstr']),str(item['issue_id']),item.get('label'),sid,date,'day' if date else None,
               'source_declared_issue_date_unverified' if date else 'unresolved',ev[:1200] or None,rec['retrieved_at'],len(tables),'Observed legacy issue links only; no claim of continuous editorial coverage.'))
            issues+=1
            if date:dates.append(date)
            for i,t in enumerate(tables,1):
                cs=t.find('tr').find_all('td',recursive=False);a=cs[0].find('a',href=lambda u:u and 'novelid=' in u)
                au=cs[1].find('a',href=lambda u:u and 'authorid=' in u) if len(cs)>1 else None
                url=urljoin('https://www.jjwxc.net/',a['href'])
                wid=qid(url,'novelid')
                if not wid.isdigit() or int(wid)==0:continue
                r=dict(platform='jjwxc',work_id=wid,title=a.get_text(' ',strip=True),author=au.get_text(' ',strip=True) if au else '',
                  author_id=qid(au['href'],'authorid') if au else '',genre_raw=cs[2].get_text(' ',strip=True) if len(cs)>2 else '',
                  status=cs[-1].get_text(' ',strip=True),work_url=url)
                key,oid=self.observe(sid,'editorial-entry:'+str(i),r,rec,'editorial_issue_date_not_publication',None,date,'official_editorial_id_observed')
                excerpt=' '.join(x.get_text(' ',strip=True) for x in t.select('td.read_small'))[:180]
                self.c.execute('INSERT OR IGNORE INTO editorial_entry VALUES(?,?,?,?,?,?)',(h(ikey,i),ikey,key,i,excerpt,oid))
                n+=1;keys.add(key)
        self.batch.append(dict(batch_id='jj_editorial',layer='editorial_selection',platform='jjwxc',source_label='JJWXC historical expert-recommendation issues',rows_imported=n,unique_work_ids=len(keys),date_start=min(dates) if dates else None,date_end=max(dates) if dates else None,limitations=f'{issues} recovered legacy issues; issue dates are not work-publication dates; display order is not rank. Unresolved issue dates remain missing.'))

    def finish(self):
        for b in self.batch:
            self.c.execute('INSERT OR REPLACE INTO batch_audit VALUES(?,?,?,?,?,?,?,?,?)',tuple(b[k] for k in ('batch_id','layer','platform','source_label','rows_imported','unique_work_ids','date_start','date_end','limitations')))
        self.c.execute('''UPDATE candidate_work SET linked_work_key=(SELECT MIN(w.work_key) FROM work_master w WHERE w.platform=candidate_work.platform AND w.title=candidate_work.title AND w.author=candidate_work.author), link_method='unique_exact_title_author_v03' WHERE linked_work_key IS NULL AND author!='' AND (SELECT COUNT(*) FROM work_master w WHERE w.platform=candidate_work.platform AND w.title=candidate_work.title AND w.author=candidate_work.author)=1''')
        self.c.executescript('''
        CREATE VIEW IF NOT EXISTS annual_catalog_sample_v03 AS
        SELECT cm.platform,cm.requested_year,cm.sort_label,COUNT(*) observations,COUNT(DISTINCT so.work_key) unique_works,COUNT(DISTINCT so.source_id) pages,MAX(cm.page) max_page
        FROM catalog_membership cm JOIN source_observation so USING(observation_id) GROUP BY 1,2,3;
        CREATE VIEW IF NOT EXISTS structured_rankings AS
        SELECT l.platform,l.list_name,l.snapshot_date,l.date_role,l.eligibility_note,e.rank,e.work_key,w.title,w.author,e.metric_value_raw,e.metric_unit,l.source_id
        FROM ranking_entry e JOIN ranking_list l USING(list_id) JOIN work_master w USING(work_key);
        CREATE VIEW IF NOT EXISTS structured_editorial AS
        SELECT i.platform,i.series,i.issue_id,i.label,i.issue_date,i.date_confidence,e.work_key,w.title,w.author,e.display_order,i.source_id
        FROM editorial_entry e JOIN editorial_issue i USING(issue_key) JOIN work_master w USING(work_key);
        ''')
        self.c.commit()
        final=dict(self.c.execute('SELECT platform,COUNT(*) FROM work_master GROUP BY platform').fetchall())
        counts={r[0]:self.c.execute('SELECT COUNT(*) FROM "'+r[0]+'"').fetchone()[0] for r in self.c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        tests={
          'sqlite_integrity':self.c.execute('PRAGMA integrity_check').fetchone()[0]=='ok',
          'foreign_keys':not self.c.execute('PRAGMA foreign_key_check').fetchall(),
          'work_count_never_decreased':all(final[k]>=v for k,v in self.initial.items()),
          'no_first_year_fabricated':self.c.execute('SELECT COUNT(*) FROM work_master WHERE first_pub_year_verified IS NOT NULL').fetchone()[0]==0,
          'no_chapter_full_text_claim':self.c.execute('SELECT COUNT(*) FROM chapter_metadata WHERE chapter_text_imported!=0').fetchone()[0]==0,
          'no_legacy_id_invented':self.c.execute('SELECT COUNT(*) FROM legacy_bibliography WHERE platform_work_id IS NOT NULL OR linked_work_key IS NOT NULL').fetchone()[0]==0,
          'no_full_catalog_claim':self.c.execute('SELECT COUNT(*) FROM catalog_membership WHERE coverage_complete!=0').fetchone()[0]==0,
          'ranking_positions_unique':not self.c.execute('SELECT list_id,rank,COUNT(*) FROM ranking_entry GROUP BY 1,2 HAVING COUNT(*)>1').fetchall(),
          'new_catalog_years_match':not self.c.execute('SELECT cm.observation_id FROM catalog_membership cm JOIN source_observation so USING(observation_id) WHERE cm.requested_year!=so.declared_pub_year').fetchall(),
          'quarantined_legacy_synthetic_preserved':self.c.execute('SELECT COALESCE(SUM(excluded_rows),0) FROM quarantine').fetchone()[0]>=1920,
        }
        tests['editorial_order_not_promoted_to_rank'] = 'rank' not in [r[1] for r in self.c.execute('PRAGMA table_info(editorial_entry)')]
        tests['all_platform_keys_valid'] = all(re.fullmatch(r'(jjwxc|qidian):[1-9]\d*', r[0]) for r in self.c.execute('SELECT work_key FROM work_master'))
        tests['no_work_publication_from_ranking_snapshot'] = self.c.execute("SELECT COUNT(*) FROM source_observation WHERE date_type='ranking_snapshot' AND declared_pub_year IS NOT NULL").fetchone()[0] == 0
        tests['new_sources_still_match_hashes'] = all(hashlib.sha256((self.out/r['file']).read_bytes()).hexdigest()==r['sha256'] for r in self.verified)
        if not all(tests.values()):raise AssertionError(tests)
        summary=dict(initial_work_counts=self.initial,final_work_counts=final,new_work_counts={k:final[k]-self.initial.get(k,0) for k in final},table_counts=counts,new_sources_hash_verified=len(self.verified),tests=tests,batches=self.batch)
        (self.out/'audit/build_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        (self.out/'audit/source_manifest_v03.json').write_text(json.dumps(self.verified,ensure_ascii=False,indent=2),encoding='utf-8')
        names=[r[0] for r in self.c.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%'")]
        for name in names:
            cur=self.c.execute('SELECT * FROM "'+name+'"')
            with (self.out/'data/derived'/f'{name}.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow([d[0] for d in cur.description]);w.writerows(cur)
        (self.out/'audit/schema_v03.sql').write_text('\n\n'.join(r[0]+';' for r in self.c.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND type IN ('table','view')")),encoding='utf-8')
        self.c.close()
        print(json.dumps(summary,ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--new',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();b=Builder(a.baseline,a.new,a.out)
    b.catalog();b.chapter_source();b.legacy();b.rankings();b.editorial();b.finish()
if __name__=='__main__':main()
