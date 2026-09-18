#!/usr/bin/env python3
"""Bounded public catalog collection. No login, paywall or challenge bypass."""
from __future__ import annotations
import argparse, hashlib, json, random, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
UA='WebnovelBibliographyResearch/0.2 (+https://github.com/huwenbo-lab/research_harness)'
BASE='https://www.jjwxc.net/bookbase.php'
DATE=re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$')
def utc(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def digest(b): return hashlib.sha256(b).hexdigest()
def clean(x): return ' '.join(str(x or '').replace('\xa0',' ').split())
def qid(url,name):
    v=parse_qs(urlparse(url).query).get(name,[''])[0]
    return v if v.isdigit() else ''
def number(t):
    s=clean(t).replace(',','')
    return int(s) if s.isdigit() else None

def parse_jjwxc(body,source_url,observed_at):
    soup=BeautifulSoup(body,'html.parser');rows=[]
    for tr in soup.select('table.cytable tr'):
        td=tr.find_all('td',recursive=False)
        if len(td)!=7: continue
        a=td[1].find('a',href=True);author=td[0].find('a',href=True)
        if a is None: continue
        work_id=qid(a['href'],'novelid')
        if not work_id: continue
        date_raw=clean(td[6].get_text(' ',strip=True));valid=False
        if DATE.fullmatch(date_raw):
            try: datetime.strptime(date_raw,'%Y-%m-%d %H:%M:%S');valid=True
            except ValueError: pass
        title=clean(a.get_text(' ',strip=True));descr=a.get('title','')
        intro,sep,tags=descr.partition('标签：');intro=intro.removeprefix('简介：').strip()
        genre=clean(td[2].get_text(' ',strip=True));bits=genre.split('-')
        rows.append(dict(platform='jjwxc',work_id=work_id,title=title,
          author=clean(author.get_text(' ',strip=True)) if author else clean(td[0].get_text()),
          author_id=qid(author['href'],'authorid') if author else '',
          date_raw=date_raw,declared_pub_year=int(date_raw[:4]) if valid else None,
          date_type='platform_catalog_publication' if valid else 'unresolved',
          first_pub_year_verified=None,date_confidence='platform_label_not_independently_verified',
          genre_raw=genre,originality=bits[0] if len(bits)>1 else '',
          orientation=bits[1] if len(bits)>2 else '',setting=bits[2] if len(bits)>3 else '',
          genre=bits[3] if len(bits)>3 else genre,viewpoint=bits[4] if len(bits)>4 else '',
          status=clean(td[3].get_text(' ',strip=True)),word_count=number(td[4].get_text()),
          points=number(td[5].get_text()),synopsis=intro,tags_raw=tags.strip(),
          work_url='https://www.jjwxc.net/onebook.php?novelid='+work_id,
          source_url=source_url,observed_at=observed_at,source_kind='live_official_catalog'))
    txt=soup.get_text(' ',strip=True);m=re.search(r'共\s*(\d+)\s*页',txt);curr=re.search(r'当前为?第\s*(\d+)\s*页',txt)
    years={}
    for inp in soup.select('input[name^="fbsj"]'):
        v=str(inp.get('value',''))
        if re.fullmatch(r'20\d{2}',v): years[int(v)]={'name':inp.get('name'),'value':v}
    nxt=next((urljoin(source_url,a['href']) for a in soup.find_all('a',href=True) if a.get_text(strip=True)=='下一页'),None)
    return rows,dict(total_pages=int(m.group(1)) if m else None,current_page=int(curr.group(1)) if curr else None,next_url=nxt,year_fields=years,encoding=soup.original_encoding,rows=len(rows))

class Collector:
    def __init__(self,out,delay=3):
        self.out=out;out.mkdir(parents=True,exist_ok=True);self.delay=max(2,delay)
        self.logs=[];self.robots={};self.blocked_hosts=set()
    def write_logs(self):
        (self.out/'retrieval_log.json').write_text(json.dumps(self.logs,ensure_ascii=False,indent=2),encoding='utf-8')
    def get(self,url,name,check_robots=True):
        host=urlparse(url).netloc
        if host!='www.jjwxc.net': raise ValueError('unexpected_source_host')
        if host in self.blocked_hosts: return None
        if check_robots and host not in self.robots:
            rb=self.get('https://'+host+'/robots.txt',host+'.robots.txt',False)
            if rb is None: self.robots[host]=None
            else:
                rp=RobotFileParser();rp.parse(rb.decode('utf-8','replace').splitlines());self.robots[host]=rp
        if check_robots and (self.robots.get(host) is None or not self.robots[host].can_fetch('WebnovelBibliographyResearch',url)):
            self.logs.append(dict(url=url,file=name,retrieved_at=utc(),status='robots_not_permitted_or_unavailable'));self.write_logs();return None
        info=dict(url=url,file=name,retrieved_at=utc())
        try:
            with urlopen(Request(url,headers={'User-Agent':UA}),timeout=18) as r:
                data=r.read(20*1024*1024+1);ct=r.headers.get('Content-Type','')
                info.update(status=r.status,content_type=ct,bytes=len(data),sha256=digest(data))
                if len(data)>20*1024*1024: raise ValueError('size_limit')
                (self.out/name).write_bytes(data)
                if r.status!=200: raise ValueError('unexpected_http_status_'+str(r.status))
                prefix=data[:3000].lower()
                if url.endswith('/robots.txt') and (b'<html' in prefix or b'<script' in prefix): raise ValueError('robots_returned_html')
                if any(x in prefix for x in [b'probe.js',b'captcha',b'cf-chl-']): raise ValueError('challenge_page')
            return data
        except Exception as e:
            info.update(error=str(e))
            if isinstance(e,HTTPError): info['status']=e.code
            if info.get('status') in (202,401,403,429) or 'challenge' in str(e): self.blocked_hosts.add(host)
            return None
        finally:
            self.logs.append(info);self.write_logs();print(json.dumps(info,ensure_ascii=False),flush=True);time.sleep(self.delay)
    def jjwxc(self,years,pages_per_year,seed):
        raw=self.get(BASE+'?orderstr=1','jjwxc_discovery.html')
        if raw is None: return
        _,config=parse_jjwxc(raw,BASE+'?orderstr=1',utc())
        (self.out/'jjwxc_discovery.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
        audits=[];output=self.out/'jjwxc_observations.jsonl';output.write_text('',encoding='utf-8')
        for year in years:
            yf=config['year_fields'].get(year)
            if not yf:
                audits.append(dict(year=year,status='year_option_absent'));continue
            url=BASE+'?'+urlencode({'version':1,'fw1':1,yf['name']:yf['value'],'sortType':2,'page':1})
            name=f'jjwxc_{year}_p00001.html';b=self.get(url,name)
            if b is None:
                audits.append(dict(year=year,status='first_page_failed'));continue
            rows,meta=parse_jjwxc(b,url,self.logs[-1]['retrieved_at']);years_found={r['declared_pub_year'] for r in rows}
            if not rows or years_found!={year}:
                audits.append(dict(year=year,status='annual_filter_unverified',years_found=sorted(str(y) for y in years_found),metadata=meta));continue
            total=meta['total_pages']
            if not total or meta['current_page']!=1:
                audits.append(dict(year=year,status='pagination_unverified',metadata=meta));continue
            targets=[1]
            if total>1: targets+=sorted(random.Random(seed+year).sample(range(2,total+1),min(pages_per_year-1,total-1)))
            signatures=set();successes=0
            for page in targets:
                if page!=1:
                    if not meta['next_url']:
                        audits.append(dict(year=year,page=page,status='no_observed_pagination_url'));continue
                    parts=urlparse(meta['next_url']);q=parse_qs(parts.query);q['page']=[str(page)]
                    url=parts._replace(query=urlencode(q,doseq=True)).geturl();name=f'jjwxc_{year}_p{page:05}.html';b=self.get(url,name)
                    if b is None: continue
                    rows,pgmeta=parse_jjwxc(b,url,self.logs[-1]['retrieved_at'])
                else: pgmeta=meta
                sig=digest('|'.join(r['work_id'] for r in rows).encode())
                valid=bool(rows) and all(r['declared_pub_year']==year for r in rows) and pgmeta['current_page']==page
                if not valid or sig in signatures:
                    audits.append(dict(year=year,page=page,status='invalid_or_repeated_page'));continue
                signatures.add(sig);successes+=1
                for pos,r in enumerate(rows,1):
                    r.update(requested_year=year,page=page,row_on_page=pos,total_pages_declared=total,
                      selection_method='audit_first_page' if page==1 else 'seeded_random_page',
                      nominal_page_inclusion_probability=1 if page==1 else min(1,(len(targets)-1)/(total-1)),
                      raw_file=name,raw_sha256=digest(b))
                with output.open('a',encoding='utf-8') as f:
                    for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
                print(f'ACCEPTED year={year} page={page}/{total} rows={len(rows)}',flush=True)
            audits.append(dict(year=year,status='complete_catalog' if successes==total else 'partial_page_sample',
              declared_pages=total,planned_pages=targets,accepted_pages=successes,year_filter_validated=True,seed=seed))
            (self.out/'jjwxc_annual_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
        (self.out/'jjwxc_annual_audit.json').write_text(json.dumps(audits,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--start',type=int,default=2005);ap.add_argument('--end',type=int,default=2025)
    ap.add_argument('--pages-per-year',type=int,default=5);ap.add_argument('--seed',type=int,default=20260918);ap.add_argument('--delay',type=float,default=3)
    a=ap.parse_args()
    if not (2003<=a.start<=a.end<=datetime.now().year) or not (1<=a.pages_per_year<=100):ap.error('invalid bounds')
    Collector(a.out,a.delay).jjwxc(list(range(a.start,a.end+1)),a.pages_per_year,a.seed)
if __name__=='__main__':main()
