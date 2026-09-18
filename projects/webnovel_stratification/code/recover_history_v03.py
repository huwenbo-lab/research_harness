#!/usr/bin/env python3
"""Recover observed editorial issue links and public CDX metadata indexes."""
from __future__ import annotations
import argparse, json, re
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs,urlencode
from urllib.robotparser import RobotFileParser
from bs4 import BeautifulSoup
from expand_sources_v03 import Fetcher,now

def editorial(f):
    base='https://www.jjwxc.net/'
    index=[]
    for order in (1,2):
        root=base+'topten.php?'+urlencode({'orderstr':order,'timeid':''})
        b=f.get(root,f'jj_editorial_index_{order}.html',robots=True,delay=3)
        if b is None:continue
        soup=BeautifulSoup(b,'html.parser'); links={}
        for a in soup.find_all('a',href=True):
            url=urljoin(root,a['href']); q=parse_qs(urlparse(url).query)
            if urlparse(url).netloc=='www.jjwxc.net' and 'topten.php' in urlparse(url).path and q.get('timeid',[''])[0].isdigit():
                if q.get('orderstr',[str(order)])[0]!=str(order):continue
                links[url]={'url':url,'issue_id':q['timeid'][0],'label':a.get_text(' ',strip=True),'orderstr':order}
        for sel in soup.find_all('select'):
            if sel.get('name')=='timeid' or sel.get('id')=='timeid':
                for option in sel.find_all('option'):
                    val=str(option.get('value',''))
                    if val.isdigit():
                        url=base+'topten.php?'+urlencode({'orderstr':order,'timeid':val})
                        links[url]={'url':url,'issue_id':val,'label':option.get_text(' ',strip=True),'orderstr':order}
        all_items=sorted(links.values(),key=lambda x:int(x['issue_id']))
        if len(all_items)>120:
            ids=sorted({round(i*(len(all_items)-1)/119) for i in range(120)})
            selected=[all_items[i] for i in ids]
        else:selected=all_items
        info=dict(orderstr=order,discovered_issues=len(all_items),selected_issues=len(selected),selection='all_observed_issues' if len(all_items)<=120 else 'evenly_spaced_issue_ids_not_probability_sample',all_issue_links=all_items,acquired=[])
        for item in selected:
            if 'www.jjwxc.net' in f.blocked:break
            name=f'jj_editorial_o{order}_issue{item["issue_id"]}.html'
            data=f.get(item['url'],name,robots=True,delay=3)
            info['acquired'].append(dict(**item,file=name,acquired=data is not None,retrieved_at=f.logs[-1]['retrieved_at']))
            (f.out/f'jj_editorial_index_{order}.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
        index.append(info)
    (f.out/'editorial_recovery.json').write_text(json.dumps(index,ensure_ascii=False,indent=2),encoding='utf-8')

def archive_api(f):
    # RFC9309 permits access when robots.txt returns 404. This is distinct from
    # timeouts, 5xx, 202 challenge responses or a real disallow rule.
    rb=f.get('https://web.archive.org/robots.txt','wayback_robots.txt')
    rp=RobotFileParser()
    if rb is not None:
        rp.parse(rb.decode('utf-8','replace').splitlines())
    elif f.logs[-1].get('status')==404:
        rp.parse(['User-agent: *','Disallow:'])
    else:
        (f.out/'wayback_skip.json').write_text(json.dumps({'reason':'robots_unreachable_or_access_control'}));return
    patterns=[('qd_monthly','www.qidian.com/rank/yuepiao*'),('qd_old','top.qidian.com/Book/TopDetail.aspx*'),('qd_r','r.qidian.com/yuepiao*'),('qd_sanjiang','www.qidian.com/book/sanjiang*'),('jj_monthly','www.jjwxc.net/topten.php?orderstr=5*'),('jj_editorial','www.jjwxc.net/topten.php?orderstr=1*')]
    for label,pattern in patterns:
        params={'url':pattern,'output':'json','filter':'statuscode:200','collapse':'timestamp:6','from':2005,'to':2025,'limit':2500}
        url='https://web.archive.org/cdx/search/cdx?'+urlencode(params)
        if not all(rp.can_fetch(a,url) for a in ('ChatGPT-User','WebnovelBibliographyResearch')):continue
        b=f.get(url,label+'_cdx.json',delay=4)
        if b is None:continue
        try: data=json.loads(b)
        except ValueError:continue
        if not isinstance(data,list) or len(data)<2:continue
        head=data[0]; captures=[dict(zip(head,x)) for x in data[1:]]
        # Preserve index independently; only a few actual HTML captures in this probe.
        selected=[]
        for year in (2005,2010,2015,2020,2025):
            hit=next((x for x in captures if str(x.get('timestamp','')).startswith(str(year))),None)
            if hit:selected.append(hit)
        for i,cap in enumerate(selected):
            u='https://web.archive.org/web/'+cap['timestamp']+'id_/'+cap['original']
            if all(rp.can_fetch(a,u) for a in ('ChatGPT-User','WebnovelBibliographyResearch')):
                f.get(u,f'{label}_capture_{i}.html',delay=4)
        (f.out/(label+'_selected_captures.json')).write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['editorial','archives']);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();f=Fetcher(a.out)
    (editorial if a.mode=='editorial' else archive_api)(f)
if __name__=='__main__':main()
