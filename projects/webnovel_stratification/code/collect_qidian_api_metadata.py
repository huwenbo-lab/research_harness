#!/usr/bin/env python3
"""Collect public Qidian bibliographic and chapter-catalog metadata.

Routes tried are public mobile/static metadata pages and catalog endpoints only.
No chapter-content endpoint is called. No login cookie, CAPTCHA solving, stealth,
or access-control bypass is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
BLOCK = (202, 401, 403, 429)
CHALLENGE = ("验证码","安全验证","访问过于频繁","请求异常","请完成验证","captcha","challenge")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_db(root: Path) -> Path:
    hits=list(root.rglob("webnovel_catalog.sqlite"))
    if not hits: raise FileNotFoundError("webnovel_catalog.sqlite not found")
    return hits[0]


def choose_ids(db: Path, offset: int, limit: int):
    con=sqlite3.connect(db); con.row_factory=sqlite3.Row
    rows=con.execute("""
      SELECT platform_work_id,title,author,status_raw,work_url
      FROM work_master
      WHERE platform='qidian' AND platform_work_id GLOB '[0-9]*'
      ORDER BY CAST(platform_work_id AS INTEGER)
    """).fetchall()
    con.close()
    if not rows: return []
    start=offset%len(rows)
    return [dict(rows[(start+i)%len(rows)]) for i in range(min(limit,len(rows)))]


def fetch(url: str, accept: str, referer: str):
    req=Request(url,headers={
      "User-Agent":UA_MOBILE,
      "Accept":accept,
      "Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7",
      "Referer":referer,
    })
    with urlopen(req,timeout=20) as r:
        status=r.status; ctype=r.headers.get("Content-Type",""); body=r.read(20*1024*1024+1)
    if len(body)>20*1024*1024: raise ValueError("size_limit")
    if status!=200: raise HTTPError(url,status,"unexpected status",{},None)
    return status,ctype,body


def page_is_challenge(body: bytes) -> bool:
    text=BeautifulSoup(body,"html.parser").get_text(" ",strip=True).lower()
    return any(x.lower() in text for x in CHALLENGE)


def parse_mobile_book(body: bytes, wid: str, url: str):
    soup=BeautifulSoup(body,"html.parser")
    metas={}
    for m in soup.find_all("meta"):
        k=m.get("property") or m.get("name") or m.get("itemprop")
        v=m.get("content")
        if k and v: metas[str(k)]=str(v)

    structured={}
    for node in soup.find_all("script",attrs={"type":"application/ld+json"}):
        raw=node.string or node.get_text()
        if not raw: continue
        try: obj=json.loads(raw)
        except Exception: continue
        candidates=[]
        if isinstance(obj,dict):
            candidates.extend(obj.get("@graph") or [])
            candidates.append(obj)
        elif isinstance(obj,list): candidates.extend(obj)
        for x in candidates:
            if not isinstance(x,dict) or x.get("@type")!="Book": continue
            ident=x.get("identifier")
            ident_value=None
            if isinstance(ident,dict): ident_value=str(ident.get("value") or "")
            if ident_value and ident_value!=str(wid): continue
            structured=x
            break
        if structured: break

    def mv(*keys):
        for k in keys:
            if metas.get(k): return metas[k]
        return None
    author_obj=structured.get("author") if isinstance(structured,dict) else None
    title=structured.get("name") if isinstance(structured,dict) else None
    title=title or mv("og:novel:book_name","og:title")
    author=(author_obj or {}).get("name") if isinstance(author_obj,dict) else None
    author=author or mv("og:novel:author","author")
    status=mv("og:novel:status")
    update=mv("og:novel:update_time","article:modified_time") or structured.get("dateModified")
    published=structured.get("datePublished") if isinstance(structured,dict) else None
    latest=mv("og:novel:latest_chapter_name")
    category=(structured.get("genre") if isinstance(structured,dict) else None) or mv("og:novel:category")
    desc=(structured.get("description") if isinstance(structured,dict) else None) or mv("og:description","description")
    if not title:
        h=soup.find("h1"); title=h.get_text(" ",strip=True) if h else None
    return {
      "book_id":wid,"title":title,"author":author,"status":status,
      "date_published":published,"date_modified":structured.get("dateModified") if isinstance(structured,dict) else None,
      "update_time":update,"latest_chapter":latest,"category":category,
      "description":desc,"source_url":url,
      "structured_data_basis":"schema.org Book JSON-LD" if structured else None,
      "meta_fields":{k:v for k,v in metas.items() if any(t in k.lower() for t in ("novel","date","time","author","title"))},
      "html_sha256":hashlib.sha256(body).hexdigest(),"html_bytes_transient":len(body),
      "note":"HTML parsed transiently for metadata only; not retained."
    }

def parse_mobile_catalog(body: bytes, wid: str, base: str):
    soup=BeautifulSoup(body,"html.parser"); raw=[]; pos=0
    date_re=re.compile(r"(?:19|20)\\d{2}-\\d{2}-\\d{2} \\d{2}:\\d{2}:\\d{2}")
    for a in soup.find_all("a",href=True):
        href=urljoin(base,a["href"]); title=a.get_text(" ",strip=True)
        if not title or wid not in href: continue
        p=urlparse(href).path.lower()
        if "/chapter/" not in p and "/read/" not in p: continue
        nums=re.findall(r"\\d+",p); cid=nums[-1] if nums else href
        dm=date_re.search(title)
        raw.append({
          "book_id":wid,"chapter_id":cid,"chapter_title":title[:300],"url":href,
          "display_time":dm.group(0) if dm else None,"source":"mobile_catalog_html","_pos":pos
        }); pos+=1

    # Mobile pages repeat the latest chapter above the actual catalog. Keep the
    # last occurrence of each chapter ID, which removes that teaser while
    # preserving catalog order.
    last_index={}
    for i,r in enumerate(raw): last_index[r["chapter_id"]]=i
    out=[]
    for i,r in enumerate(raw):
        if last_index[r["chapter_id"]]!=i: continue
        r.pop("_pos",None); out.append(r)
    return out

def flatten_json_catalog(obj, wid: str, source: str):
    out=[]
    data=obj.get("data") if isinstance(obj,dict) else None
    def walk(x,vol=None):
        if isinstance(x,dict):
            nvol=vol
            for k in ("vN","volumeName","volume_name","volName"):
                if x.get(k): nvol=str(x[k]); break
            cid=x.get("cU") or x.get("chapterId") or x.get("chapter_id")
            title=x.get("cN") or x.get("chapterName") or x.get("chapter_name")
            if cid is not None and title:
                out.append({
                  "book_id":wid,"chapter_id":str(cid),"chapter_title":str(title),
                  "volume":nvol,"vip":x.get("isVip") if "isVip" in x else x.get("vipStatus"),
                  "update_time":x.get("updateTime") or x.get("updTime"),
                  "publish_time":x.get("publishTime") or x.get("createTime"),
                  "source":source,
                })
            for v in x.values(): walk(v,nvol)
        elif isinstance(x,list):
            for v in x: walk(v,vol)
    walk(data)
    seen=set(); clean=[]
    for r in out:
        key=(r["chapter_id"],r["chapter_title"])
        if key in seen: continue
        seen.add(key); clean.append(r)
    return clean


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--baseline",required=True); ap.add_argument("--out",required=True)
    ap.add_argument("--offset",type=int,default=0); ap.add_argument("--limit",type=int,default=50)
    ap.add_argument("--delay",type=float,default=3.0)
    args=ap.parse_args()

    out=Path(args.out); out.mkdir(parents=True,exist_ok=False)
    seeds=choose_ids(find_db(Path(args.baseline)),args.offset,args.limit)
    (out/"seed_batch.json").write_text(json.dumps(seeds,ensure_ascii=False,indent=2),encoding="utf-8")

    records=[]; chapters=[]; logs=[]; blocked_hosts=set()
    for seed in seeds:
        wid=seed["platform_work_id"]
        rec={"seed":seed,"work_id":wid,"observed_at":utcnow(),"routes":[]}

        book_url=f"https://m.qidian.com/book/{wid}/"
        host=urlparse(book_url).hostname
        if host not in blocked_hosts:
            log={"work_id":wid,"kind":"mobile_work","url":book_url,"started_at":utcnow()}
            try:
                status,ctype,body=fetch(book_url,"text/html,application/xhtml+xml,*/*;q=0.8","https://m.qidian.com/")
                challenged=page_is_challenge(body)
                info=parse_mobile_book(body,wid,book_url)
                log.update(status=status,content_type=ctype,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),challenged=challenged,parsed_title=bool(info.get("title")))
                if challenged or status in BLOCK: blocked_hosts.add(host)
                elif info.get("title"): rec["info"]=info
                rec["routes"].append({"kind":"mobile_work","status":status,"challenged":challenged,"parsed_title":bool(info.get("title"))})
            except HTTPError as e:
                log.update(status=e.code,error=repr(e))
                if e.code in BLOCK: blocked_hosts.add(host)
            except Exception as e: log["error"]=repr(e)
            logs.append(log); time.sleep(max(2,args.delay))

        catalog_candidates=[]
        mobile_catalog=f"https://m.qidian.com/book/{wid}/catalog/"
        mh=urlparse(mobile_catalog).hostname
        if mh not in blocked_hosts:
            log={"work_id":wid,"kind":"mobile_catalog","url":mobile_catalog,"started_at":utcnow()}
            try:
                status,ctype,body=fetch(mobile_catalog,"text/html,application/xhtml+xml,*/*;q=0.8",book_url)
                challenged=page_is_challenge(body)
                rows=parse_mobile_catalog(body,wid,mobile_catalog) if not challenged else []
                log.update(status=status,content_type=ctype,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),challenged=challenged,chapter_rows=len(rows))
                if challenged or status in BLOCK: blocked_hosts.add(mh)
                catalog_candidates.append(("mobile_catalog_html",rows))
                rec["routes"].append({"kind":"mobile_catalog","status":status,"challenged":challenged,"chapter_rows":len(rows)})
            except HTTPError as e:
                log.update(status=e.code,error=repr(e))
                if e.code in BLOCK: blocked_hosts.add(mh)
            except Exception as e: log["error"]=repr(e)
            logs.append(log); time.sleep(max(2,args.delay))

        for kind,url in (
          ("read_ajax_catalog",f"https://read.qidian.com/ajax/book/category?bookId={wid}"),
          ("book_ajax_catalog",f"https://book.qidian.com/ajax/book/category?bookId={wid}"),
        ):
            host=urlparse(url).hostname
            if host in blocked_hosts: continue
            log={"work_id":wid,"kind":kind,"url":url,"started_at":utcnow()}
            try:
                status,ctype,body=fetch(url,"application/json,text/javascript,*/*;q=0.1",book_url)
                obj=json.loads(body.decode("utf-8","replace"))
                rows=flatten_json_catalog(obj,wid,kind)
                log.update(status=status,content_type=ctype,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),api_code=obj.get("code") if isinstance(obj,dict) else None,chapter_rows=len(rows))
                catalog_candidates.append((kind,rows))
                rec["routes"].append({"kind":kind,"status":status,"chapter_rows":len(rows),"api_code":obj.get("code") if isinstance(obj,dict) else None})
            except HTTPError as e:
                log.update(status=e.code,error=repr(e))
                if e.code in BLOCK: blocked_hosts.add(host)
            except Exception as e: log["error"]=repr(e)
            logs.append(log); time.sleep(max(2,args.delay))

        best=max(catalog_candidates,key=lambda x:len(x[1]),default=(None,[]))
        rec["catalog_source"]=best[0]; rec["chapter_count"]=len(best[1])
        rec["first_chapter"]=best[1][0] if best[1] else None
        rec["last_chapter"]=best[1][-1] if best[1] else None
        ending_re=re.compile(r"全文完|全书完|正文完|大结局|终章|完结章")
        ending_rows=[x for x in best[1] if ending_re.search(x.get("chapter_title") or "")]
        rec["ending_chapter_candidate"]=ending_rows[-1] if ending_rows else None
        chapters.extend(best[1]); records.append(rec)

        (out/"retrieval_log.json").write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding="utf-8")
        with (out/"qidian_api_metadata.jsonl").open("w",encoding="utf-8") as f:
            for x in records: f.write(json.dumps(x,ensure_ascii=False)+"\n")
        with (out/"qidian_chapter_catalog.jsonl").open("w",encoding="utf-8") as f:
            for x in chapters: f.write(json.dumps(x,ensure_ascii=False)+"\n")

        if {"m.qidian.com","read.qidian.com","book.qidian.com"}.issubset(blocked_hosts): break

    summary={
      "requested_seed_count":len(seeds),"completed_work_count":len(records),
      "works_with_title":sum(bool((x.get("info") or {}).get("title")) for x in records),
      "works_with_catalog":sum((x.get("chapter_count") or 0)>0 for x in records),
      "chapter_rows":len(chapters),"blocked_hosts":sorted(blocked_hosts),
      "created_at":utcnow(),
      "scope":"public bibliographic/chapter-catalog metadata only; no chapter content endpoint called",
    }
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__": main()
