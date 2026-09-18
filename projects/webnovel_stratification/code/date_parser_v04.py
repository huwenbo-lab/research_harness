"""Conservative date-role extraction from official metadata and chapter tables.

Dates on chapter lists are updates unless the page explicitly labels otherwise.
Ending-title markers are candidates, never independently verified completion dates.
"""
from __future__ import annotations
import re
from datetime import datetime
from urllib.parse import urljoin,urlparse,parse_qs
from bs4 import BeautifulSoup

DATE_RE=re.compile(r'(?<!\d)((?:19|20)\d{2})[-/年](\d{1,2})[-/月](\d{1,2})(?:日)?(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?')

def text(x):return ' '.join(str(x or '').replace('\xa0',' ').split())
def date_value(raw):
    m=DATE_RE.search(str(raw or ''))
    if not m:return None
    try:
        y,mo,d,hh,mi,ss=m.groups();dt=datetime(int(y),int(mo),int(d),int(hh or 0),int(mi or 0),int(ss or 0))
        return dt.isoformat(sep=' ') if hh is not None else dt.date().isoformat()
    except ValueError:return None

def end_role(title):
    s=text(title)
    if any(v in s for v in ('未完','未结','不完结','假结局','完结倒计','完结预告','完结感言','结局上','结局（上','结局(上')):return None
    if re.search(r'全文[终完]|全书[终完]|全文[已]?完结',s):return 'all_text_end_marker_update'
    if re.search(r'正文[已]?完结|正文完|正文[终]章',s):return 'main_story_end_marker_update'
    if re.search(r'大结局|完结章',s) or re.fullmatch(r'(?:\d+[ .、]*)?完结[!！。\s]*(?:\[VIP\])?',s):return 'ending_marker_update'
    return None

def parse_jj_detail(body:bytes,work_id:str,url:str):
    soup=BeautifulSoup(body,'html.parser')
    title_node=soup.select_one('[itemprop="articleSection"]')
    title=text(title_node.get_text()) if title_node else None
    author_node=soup.select_one('[itemprop="author"]')
    author=text(author_node.get_text()) if author_node else None
    fields={}
    for node in soup.select('meta[itemprop],meta[property],meta[name]'):
        key=node.get('itemprop') or node.get('property') or node.get('name')
        if node.get('content'):fields[key]=node['content']
    date_meta=[]
    for key,val in fields.items():
        if key.lower() in ('datepublished','datecreated','datemodified','og:novel:update_time') and date_value(val):
            date_meta.append(dict(field=key,date_raw=val,date_value=date_value(val)))
    chunks=[]
    for li in soup.find_all('li'):
        s=text(li.get_text(' ',strip=True))
        if s.startswith(('文章进度','全文字数','文章类型','作品视角','签约状态')) and len(s)<300:chunks.append(s)
    status=None
    for s in chunks:
        if s.startswith('文章进度'):status=s.split('：',1)[-1].split(':',1)[-1].strip()
    chapters=[];seen=set()
    for a in soup.find_all('a',href=True):
        u=urljoin(url,a['href']);q=parse_qs(urlparse(u).query)
        if q.get('novelid')!=[work_id] or not q.get('chapterid',[''])[0].isdigit():continue
        cid=q['chapterid'][0];tr=a.find_parent('tr')
        if tr is None or cid in seen:continue
        cells=tr.find_all('td',recursive=False)
        if len(cells)<3:continue
        dates=[]
        for td in cells:
            ds=date_value(td.get_text(' ',strip=True))
            if ds:dates.append((ds,text(td.get_text(' ',strip=True))))
        if not dates:continue
        ch_title=text(a.get_text(' ',strip=True));updated,raw=dates[-1]
        seen.add(cid)
        chapters.append(dict(chapter_id=cid,chapter_number_raw=text(cells[0].get_text()),chapter_title=ch_title,
            chapter_url=u,word_count_raw=text(cells[-2].get_text()) if len(cells)>3 else None,
            update_time_as_supplied=updated,date_raw=raw,
            date_semantics='official_chapter_list_update_not_first_publication',end_role=end_role(ch_title)))
    chapters.sort(key=lambda c:int(c['chapter_id']))
    return dict(work_id=work_id,title=title,author=author,status=status,metadata_fields=fields,date_meta=date_meta,
                metadata_lines=chunks,chapters=chapters,encoding=soup.original_encoding)
