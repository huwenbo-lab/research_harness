#!/usr/bin/env python3
"""Acquire public bibliographic metadata; never infer completion from last update.

Uses observed catalog next-page links and known work IDs. Stops on authentication,
rate limits and challenge pages. Repository inputs are downloaded as inert data,
never executed. No cookies, account credentials or novel full text are collected.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, quote, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from collect_catalog import parse_jjwxc

UA = 'WebnovelBibliographyResearch/0.4 (+https://github.com/huwenbo-lab/research_harness)'
def utc(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def sha(b): return hashlib.sha256(b).hexdigest()
def save(path, data): path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

class Fetcher:
    def __init__(self, out):
        self.out=Path(out); self.out.mkdir(parents=True,exist_ok=False)
        self.logs=[]; self.blocked=set(); self.robots={}; self.previous={}
    def get(self,url,name,robots=False,delay=1):
        host=urlparse(url).netloc
        if host in self.blocked: return None
        if robots and host not in self.robots:
            b=self.get('https://'+host+'/robots.txt',host+'.robots.txt',delay=4)
            rp=None
            if b is not None and b'<html' not in b[:1000].lower() and b'<script' not in b[:1000].lower():
                rp=RobotFileParser(); rp.parse(b.decode('utf-8','replace').splitlines())
            self.robots[host]=rp
        if robots:
            rp=self.robots[host]
            if rp is None or not rp.can_fetch('WebnovelBibliographyResearch',url):
                self.logs.append(dict(url=url,file=name,status='robots_unavailable_or_disallow',retrieved_at=utc()))
                save(self.out/'retrieval_log.json',self.logs);return None
            delay=max(4,delay,rp.crawl_delay('WebnovelBibliographyResearch') or 0)
        wait=delay-(time.monotonic()-self.previous.get(host,0))
        if wait>0: time.sleep(wait)
        rlog=dict(url=url,file=name,retrieved_at=utc())
        try:
            with urlopen(Request(url,headers={'User-Agent':UA}),timeout=18) as r:
                b=r.read(55*1024*1024+1)
                rlog.update(status=r.status,final_url=r.url,content_type=r.headers.get('Content-Type',''),bytes=len(b),sha256=sha(b))
                if len(b)>55*1024*1024: raise ValueError('size_limit')
                if r.status!=200: raise ValueError('unexpected_http_'+str(r.status))
                if 'text/html' in rlog['content_type']:
                    prefix=b[:3000].lower()
                    if any(s in prefix for s in (b'probe.js',b'cf-chl-',b'captcha')): raise ValueError('challenge_page')
                    text=BeautifulSoup(b,'html.parser').get_text(' ',strip=True)
                    if re.search(r'请\s*(?:登录|登入)\s*后再访问',text):raise ValueError('authentication_required')
                (self.out/name).write_bytes(b)
                return b
        except Exception as e:
            rlog['error']=str(e)
            if isinstance(e,HTTPError):rlog['status']=e.code
            if rlog.get('status') in (202,401,403,429) or 'challenge' in str(e) or 'authentication_required' in str(e):self.blocked.add(host)
            return None
        finally:
            self.previous[host]=time.monotonic();self.logs.append(rlog)
            save(self.out/'retrieval_log.json',self.logs)
            print(json.dumps(rlog,ensure_ascii=False),flush=True)


def find_next(soup,url):
    return next((urljoin(url,a['href']) for a in soup.find_all('a',href=True) if a.get_text(strip=True)=='下一页'),None)


def jjwxc(base,out):
    f=Fetcher(out); db=next(base.rglob('webnovel_catalog.sqlite'))
    c=sqlite3.connect(db);c.row_factory=sqlite3.Row
    # Reproducible technical audit, NOT a probability sample for substantive inference.
    selected=[]
    for year in range(2005,2026):
        rows=c.execute("SELECT * FROM work_master WHERE platform='jjwxc' AND platform_declared_pub_year=? ORDER BY platform_work_id",(year,)).fetchall()
        completed=[r for r in rows if r['status_raw'] and '完成' in r['status_raw']]
        pool=completed or rows
        if pool:
            selected.append(dict(pool[len(pool)//2]))
            if year in (2010,2015,2020,2025) and len(pool)>1:selected.append(dict(pool[len(pool)//3]))
    missing=c.execute("SELECT * FROM work_master WHERE platform='jjwxc' AND platform_declared_pub_year IS NULL AND title IS NOT NULL ORDER BY platform_work_id LIMIT 12").fetchall()
    selected.extend(dict(r) for r in missing)
    save(f.out/'detail_sample.json',selected)
    manifest=[]
    for r in selected:
        if 'www.jjwxc.net' in f.blocked:break
        wid=r['platform_work_id'];url='https://www.jjwxc.net/onebook.php?novelid='+wid;name='jj_detail_'+wid+'.html'
        b=f.get(url,name,robots=True,delay=4)
        manifest.append(dict(work_key=r['work_key'],url=url,file=name,acquired=b is not None))
        save(f.out/'detail_manifest.json',manifest)
    # Resume only known public catalog links. Never request page 11 or change
    # subfilters to circumvent the already observed deep-pagination login gate.
    summary_files=list(base.rglob('*catalog_pagination_pagination_summary.json'))
    if not summary_files:
        summary_files=list(base.rglob('pagination_summary.json'))
    if not summary_files:raise ValueError('Missing observed pagination checkpoint')
    states=json.loads(summary_files[0].read_text())['years']; audits=[]
    obs=f.out/'catalog_observations.jsonl';obs.write_text('',encoding='utf-8')
    # Page-first traversal gives every incomplete year an equal expansion budget.
    for page in range(4,11):
        for year in range(2005,2026):
            if 'www.jjwxc.net' in f.blocked:break
            state=states.get(str(year),{})
            if state.get('last_page',0)!=page-1 or not state.get('next'):continue
            url=state['next'];q=parse_qs(urlparse(url).query)
            if q.get('page')!=[str(page)]:continue
            name=f'jj_catalog_{year}_sort3_p{page:02}.html';b=f.get(url,name,robots=True,delay=4)
            if b is None:
                audits.append(dict(year=year,page=page,status='fetch_failed'));continue
            rows,meta=parse_jjwxc(b,url,f.logs[-1]['retrieved_at'])
            valid=bool(rows) and meta['current_page']==page and {r['declared_pub_year'] for r in rows}=={year}
            if not valid:
                audits.append(dict(year=year,page=page,status='page_or_year_invalid'));continue
            known=set(state.get('ids',[]));ids={r['work_id'] for r in rows}
            if ids and ids==known:
                audits.append(dict(year=year,page=page,status='repeated_page'));continue
            for pos,r in enumerate(rows,1):
                r.update(requested_year=year,page=page,row_on_page=pos,sort_label='latest_publication',raw_file=name,raw_sha256=sha(b))
            with obs.open('a',encoding='utf-8') as fp:
                for r in rows:fp.write(json.dumps(r,ensure_ascii=False)+'\n')
            state.update(last_page=page,next=meta['next_url'],ids=sorted(ids))
            audits.append(dict(year=year,page=page,status='accepted',rows=len(rows),url=url,file=name))
            save(f.out/'pagination_audit.json',audits);save(f.out/'pagination_checkpoint.json',states)
        if 'www.jjwxc.net' in f.blocked:break
    save(f.out/'pagination_audit.json',audits)


def repositories(out):
    f=Fetcher(out); manifest=[]
    # Search is restricted to repository metadata; downloaded artifacts remain
    # candidates until their schema, sample provenance and authenticity are audited.
    repos=['shaido987/novel-dataset','dylan-byte-max/novel-tracker','cdykkk/jinjiang','zhangchenyangwx/jinjiangzuoye614','GuanLdong/QidianScrapy','camelboat/Qidian_Scrapy','Dengqlbq/NovelSpiderAndWordcloud']
    for i,q in enumerate(['qidian csv in:readme','晋江 数据 in:readme','起点 数据集 in:readme']):
        b=f.get('https://api.github.com/search/repositories?'+urlencode({'q':q,'per_page':8}),'search_'+str(i)+'.json',delay=7)
        if b:
            for r in json.loads(b).get('items',[]):
                if not r.get('fork') and r.get('size',0)<150000:repos.append(r['full_name'])
    for repo in list(dict.fromkeys(repos))[:22]:
        prefix=repo.replace('/','__')
        b=f.get('https://api.github.com/repos/'+repo,prefix+'__repo.json')
        if not b:continue
        info=json.loads(b);branch=info['default_branch']
        b=f.get('https://api.github.com/repos/'+repo+'/git/trees/'+quote(branch,safe='')+'?recursive=1',prefix+'__tree.json')
        if not b:continue
        tree=json.loads(b);root=tree.get('sha');entries=tree.get('tree',[])
        item=dict(repo=repo,commit_sha=root,tree_truncated=tree.get('truncated'),files=[])
        for entry in entries:
            path=entry['path'];low=path.lower();ext=Path(low).suffix
            if entry.get('type')!='blob' or entry.get('size',0)>50*1024*1024:continue
            if any(t in low for t in ['node_modules','package-lock','yarn.lock','venv/','dist/','build/','secrets','cookie','token','config','credentials','user','review','comment','history/','font','generate_sample']):continue
            document=Path(low).name in ('readme.md','license','license.md','license.txt')
            data=ext in ('.csv','.db','.sqlite','.sqlite3','.xlsx','.xls','.json') and entry.get('size',0)>5000 and (any(t in low for t in ['book','novel','data','qidian','jinjiang','jjwxc','小说','晋江','起点']) or '/' not in low)
            if not(document or data):continue
            if len([r for r in item['files'] if r['kind']=='data_candidate'])>=4 and data:continue
            name=prefix+'__'+path.replace('/','__')
            url='https://raw.githubusercontent.com/'+repo+'/'+root+'/'+quote(path,safe='/')
            payload=f.get(url,name)
            check=payload is not None and hashlib.sha1(b'blob '+str(len(payload)).encode()+b'\0'+payload).hexdigest()==entry['sha']
            item['files'].append(dict(path=path,file=name,url=url,kind='documentation' if document else 'data_candidate',git_blob_sha=entry['sha'],git_blob_verified=check,acquired=payload is not None))
        manifest.append(item);save(f.out/'repository_manifest.json',manifest)
    # Metadata-only institutional API. Do not download comments or user profiles.
    url='https://dataverse.nl/api/datasets/:persistentId/?persistentId=doi:10.34894/GQXX3K'
    b=f.get(url,'dataverse_manifest.json')
    if b:
        obj=json.loads(b);files=obj.get('data',{}).get('latestVersion',{}).get('files',[])
        for r in files:
            meta=r.get('dataFile',{});label=meta.get('filename','');low=label.lower()
            if r.get('restricted') or meta.get('filesize',0)>30*1024*1024:continue
            if 'chapter' in low and 'date' in low:
                f.get('https://dataverse.nl/api/access/datafile/'+str(meta['id']),'dv_'+Path(label).name,delay=2)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['jjwxc','repositories']);ap.add_argument('--baseline',type=Path,default=Path('baseline'));ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    if a.mode=='jjwxc':jjwxc(a.baseline,a.out)
    else:repositories(a.out)
