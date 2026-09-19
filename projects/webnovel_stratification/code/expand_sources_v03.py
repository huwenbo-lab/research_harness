#!/usr/bin/env python3
"""Recover public metadata, public catalog samples and archive indexes.

No credential use, CAPTCHA solving, stealth browser, paywall or login bypass.
Downloads remain research inputs until their semantics and provenance are audited.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, urljoin, urlencode, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from collect_catalog import parse_jjwxc

UA = 'WebnovelBibliographyResearch/0.3 (ChatGPT-User; +https://github.com/huwenbo-lab/research_harness)'
MAX_BYTES = 30 * 1024 * 1024

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def clean(x):
    return ' '.join(str(x or '').split())

class Fetcher:
    def __init__(self, out):
        self.out = Path(out)
        self.out.mkdir(parents=True, exist_ok=False)
        self.logs = []
        self.blocked = set()
        self.robots = {}
        self.last = {}
        self.byte_total = 0

    def save_log(self, rec):
        self.logs.append(rec)
        (self.out/'retrieval_log.json').write_text(json.dumps(self.logs, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(rec, ensure_ascii=False), flush=True)

    def get(self, url, name, robots=False, delay=1.0):
        host = urlparse(url).netloc
        rec = dict(url=url, file=name, retrieved_at=now())
        if host in self.blocked:
            rec['error'] = 'host_stopped_after_access_control'
            self.save_log(rec)
            return None
        if self.byte_total > 180*1024*1024:
            rec['error'] = 'batch_byte_budget'
            self.save_log(rec)
            return None
        if robots:
            if host not in self.robots:
                rb = self.get('https://'+host+'/robots.txt', host+'.robots.txt')
                rp = None
                if rb and not re.search(br'<(?:html|script)', rb[:2000], re.I):
                    rp = RobotFileParser()
                    rp.parse(rb.decode('utf-8','replace').splitlines())
                self.robots[host] = rp
            rp = self.robots[host]
            if rp is None or not all(rp.can_fetch(agent,url) for agent in ('ChatGPT-User','WebnovelBibliographyResearch')):
                rec['error'] = 'robots_not_permitted_or_unavailable'
                self.save_log(rec)
                return None
            delay = max(delay, rp.crawl_delay('ChatGPT-User') or 0, rp.crawl_delay('WebnovelBibliographyResearch') or 0)
        time.sleep(max(0,delay-(time.monotonic()-self.last.get(host,0))))
        try:
            req = Request(url, headers={'User-Agent':UA, 'Accept':'*/*'})
            with urlopen(req, timeout=20) as r:
                data = r.read(MAX_BYTES+1)
                rec.update(status=r.status, final_url=r.url, bytes=len(data), content_type=r.headers.get('Content-Type',''))
            self.last[host] = time.monotonic()
            if len(data)>MAX_BYTES:
                raise ValueError('response_size_limit')
            self.byte_total += len(data)
            rec['sha256'] = hashlib.sha256(data).hexdigest()
            (self.out/name).write_bytes(data)
            if rec['status']!=200:
                if rec['status'] in (202,401,403,429): self.blocked.add(host)
                raise ValueError('unexpected_status')
            if robots and re.search(br'probe\.js|cf-chl-',data[:4000],re.I):
                self.blocked.add(host)
                raise ValueError('challenge_page')
            if robots and 'html' in rec['content_type']:
                text=BeautifulSoup(data,'html.parser').get_text(' ',strip=True)
                if re.search(r'请\s*(?:登入|登录)\s*后再访问',text):
                    self.blocked.add(host)
                    raise ValueError('authentication_required')
            return data
        except Exception as exc:
            rec['error']=str(exc)
            if isinstance(exc,HTTPError):
                rec['status']=exc.code
                if exc.code in (401,403,429): self.blocked.add(host)
            return None
        finally:
            self.last[host]=time.monotonic()
            self.save_log(rec)

    def js(self,url,name):
        data=self.get(url,name)
        if data is None: return None
        try: return json.loads(data)
        except ValueError: return None

REPOS = [
 ('dev-chenxing/jjwxc-scraper','main'),
 ('Rodrian7/jinjiang-spider','master'),
 ('cdykkk/jinjiang','master'),
 ('1158873864/jinjiang','master'),
 ('trial-ox/qidian_yuepiao_top100','ture'),
 ('xyauhideto/qidian','master'),
 ('Tooooommy/requests_spider','master'),
 ('laujjxx/NovelCrawler','master'),
 ('dnslin/booklist','main'),
 ('Admin6016/qidian_novel_optimization','main'),
 ('liucong2013/qidiantu-filter','master'),
 ('github123520/shudan','main'),
 ('lanmaoxinqing/python-qidian-recommend','master'),
 ('positivepeng/NovelSpider','master'),
 ('yokowh/novelDataAnalysis','master'),
 ('wanfb/Text-Mining-of-Qidian-Website','master'),
]

def recover_repositories(f):
    index=[]
    for repo,branch in REPOS:
        prefix=repo.replace('/','__')
        commit=f.js(f'https://api.github.com/repos/{repo}/commits/{quote(branch,safe="")}',prefix+'__commit.json')
        if not commit: continue
        sha=commit.get('sha')
        tree_sha=commit.get('commit',{}).get('tree',{}).get('sha')
        if not sha or not tree_sha: continue
        tree=f.js(f'https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1',prefix+'__tree.json')
        if not tree: continue
        found=[]
        for entry in tree.get('tree',[]):
            p=entry.get('path',''); low=p.lower(); size=entry.get('size',0)
            if entry.get('type')!='blob': continue
            if re.search(r'(^|/)(node_modules|venv|\.venv|site-packages|fonts|\.git)(/|$)',low): continue
            suffix=Path(p).suffix.lower()
            metadata=suffix in ('.csv','.tsv','.sqlite','.sqlite3','.db','.sql','.xlsx')
            metadata=metadata or (suffix=='.json' and re.search(r'(^|/)(data|dataset|datasets|results|output|exports)(/|$)',low) is not None)
            doc=Path(low).name in ('readme.md','readme','license','license.md')
            if (metadata or doc) and 0<size<=MAX_BYTES:
                found.append(dict(path=p,size=size,git_blob_sha=entry.get('sha'),kind='metadata_candidate' if metadata else 'documentation'))
        # Documentation first; preserve all candidate paths even if the budget stops downloads.
        found.sort(key=lambda x:(x['kind']!='documentation', x['size'],x['path']))
        rec=dict(repo=repo,commit_sha=sha,commit_time=commit.get('commit',{}).get('committer',{}).get('date'),tree_truncated=tree.get('truncated'),candidates=found)
        for entry in found[:15]:
            url=f'https://raw.githubusercontent.com/{repo}/{sha}/'+quote(entry['path'],safe='/')
            name=prefix+'__'+entry['path'].replace('/','__')
            data=f.get(url,name)
            entry['local_file']=name
            entry['downloaded']=data is not None
            if data is not None:
                actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
                entry['git_blob_verified']=actual==entry['git_blob_sha']
        index.append(rec)
        (f.out/'repository_sources.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')

def collect_jjwxc(f):
    base='https://www.jjwxc.net/'
    body=f.get(base+'bookbase.php?orderstr=1','jjwxc_discovery.html',robots=True,delay=3)
    if body is None:return
    soup=BeautifulSoup(body,'html.parser')
    sorts={o.get_text(strip=True):o['value'] for o in soup.select('select[name="sortType"] option')}
    years={int(i['value']):i['name'] for i in soup.select('input[name^="fbsj"]') if str(i.get('value','')).isdigit() and len(str(i.get('value','')))==4}
    discovered=[]
    for a in soup.find_all('a',href=True):
        text=a.get_text(' ',strip=True);u=urljoin(base,a['href'])
        if urlparse(u).netloc=='www.jjwxc.net' and ('月度排行榜'==text or '官推' in text):
            if u not in [r['url'] for r in discovered]:discovered.append(dict(label=text,url=u))
    (f.out/'jjwxc_form.json').write_text(json.dumps(dict(sorts=sorts,years=years,rank_links=discovered),ensure_ascii=False,indent=2),encoding='utf-8')
    ranks=[]
    for i,item in enumerate(discovered):
        name=f'jjwxc_rank_{i:02}.html'
        b=f.get(item['url'],name,robots=True,delay=3)
        ranks.append(dict(**item,file=name,acquired=b is not None))
    (f.out/'jjwxc_ranking_sources.json').write_text(json.dumps(ranks,ensure_ascii=False,indent=2),encoding='utf-8')
    audits=[];rowsfile=f.out/'jjwxc_catalog_observations.jsonl'
    rowsfile.write_text('',encoding='utf-8')
    for label in ('随机排序','最新发表'):
        if label not in sorts: continue
        for year in range(2005,2026):
            if 'www.jjwxc.net' in f.blocked:break
            if year not in years:continue
            q={'version':'1','fw1':'1',years[year]:str(year),'sortType':sorts[label],'page':'1'}
            url=base+'bookbase.php?'+urlencode(q)
            name=f'jjwxc_{year}_sort{sorts[label]}_page1.html'
            b=f.get(url,name,robots=True,delay=3)
            audit=dict(year=year,sort_label=label,sort_value=sorts[label],url=url,file=name)
            if b is None:
                audit['status']='request_failed';audits.append(audit);continue
            observed=f.logs[-1]['retrieved_at']
            rows,meta=parse_jjwxc(b,url,observed)
            valid=bool(rows) and all(r['declared_pub_year']==year for r in rows)
            audit.update(rows=len(rows),unique_ids=len({r['work_id'] for r in rows}),year_filter_validated=valid,pagination=meta,status='partial_public_first_page' if valid else 'invalid_year_filter')
            if valid:
                with rowsfile.open('a',encoding='utf-8') as out:
                    for k,r in enumerate(rows,1):
                        r.update(raw_file=name,row_on_page=k,requested_year=year,sort_label=label,source_kind='live_official_catalog',sampling_note='platform_random_order_not_a_verified_probability_sample' if label=='随机排序' else 'latest_first_public_page')
                        out.write(json.dumps(r,ensure_ascii=False)+'\n')
            audits.append(audit)
            (f.out/'jjwxc_catalog_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
    # A single ordinary next-page test, after preserving public first-page evidence.
    # Follow an actually observed next URL and stop the host if authentication is required.
    if audits and 'www.jjwxc.net' not in f.blocked:
        nxt=next((a.get('pagination',{}).get('next_url') for a in audits if a.get('pagination',{}).get('next_url')),None)
        if nxt:f.get(nxt,'jjwxc_next_page_access_test.html',robots=True,delay=3)

def archive_indexes(f):
    targets=[
      ('qd_monthly','www.qidian.com/rank/yuepiao/*'),
      ('qd_old_monthly','top.qidian.com/Book/TopDetail.aspx*'),
      ('qd_editorial','www.qidian.com/book/strongrec*'),
      ('jj_ranks','www.jjwxc.net/topten.php*'),
    ]
    for name,pattern in targets:
        query=urlencode({'url':pattern,'output':'json','filter':'statuscode:200','collapse':'timestamp:6','from':'2005','to':'2025','limit':'2000'})
        f.get('https://web.archive.org/cdx/search/cdx?'+query,name+'_cdx.json',robots=True,delay=4)
    info=f.js('https://index.commoncrawl.org/collinfo.json','commoncrawl_collections.json')
    if isinstance(info,list):
        for year in ('2015','2020','2025'):
            hit=next((x for x in info if x.get('id','').startswith('CC-MAIN-'+year)),None)
            if hit:
                q=urlencode({'url':'www.qidian.com/rank/yuepiao/*','output':'json','filter':'status:200','pageSize':2})
                f.get(hit['cdx-api']+'?'+q,'commoncrawl_qidian_'+year+'.jsonl',delay=4)
    # Official site check only; stop on HTTP202/challenge and do not try alternate identities.
    f.get('https://www.qidian.com/rank/yuepiao/','qidian_monthly_access_test.html',robots=True,delay=3)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('mode',choices=['repos','jjwxc','archives'])
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();f=Fetcher(args.out)
    {'repos':recover_repositories,'jjwxc':collect_jjwxc,'archives':archive_indexes}[args.mode](f)

if __name__=='__main__':main()
