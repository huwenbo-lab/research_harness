#!/usr/bin/env python3
"""Discover Qidian works from the public mobile category library.

Collects bibliographic listing JSON only. It does not request chapter content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPCookieProcessor
from http.cookiejar import CookieJar

BASE="https://m.qidian.com/webcommon/category/list"
UA="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
BLOCK=(202,401,403,429)


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def session():
    jar=CookieJar(); opener=build_opener(HTTPCookieProcessor(jar))
    prime="https://m.qidian.com/category/"
    req=Request(prime,headers={
      "User-Agent":UA,"Accept":"text/html,application/xhtml+xml,*/*;q=0.8",
      "Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7",
    })
    with opener.open(req,timeout=20) as r:
        body=r.read(2*1024*1024)
        if r.status!=200: raise HTTPError(prime,r.status,"prime failed",{},None)
    token=next((x.value for x in jar if x.name=="_csrfToken"),"")
    return opener,token


def fetch_json(opener, url, referer):
    req=Request(url,headers={
      "User-Agent":UA,
      "Accept":"application/json,text/plain,*/*",
      "Accept-Language":"zh-CN,zh;q=0.9,en;q=0.7",
      "Referer":referer,
      "X-Requested-With":"XMLHttpRequest",
    })
    with opener.open(req,timeout=20) as r:
        status=r.status; ctype=r.headers.get("Content-Type",""); body=r.read(10*1024*1024+1)
    if len(body)>10*1024*1024: raise ValueError("size_limit")
    if status!=200: raise HTTPError(url,status,"unexpected status",{},None)
    return status,ctype,body,json.loads(body.decode("utf-8","replace"))


def parse(payload, gender, page):
    if not isinstance(payload,dict): return [],{}
    data=payload.get("data") or {}
    rows=data.get("records") or []
    out=[]
    for pos,x in enumerate(rows,1):
        if not isinstance(x,dict): continue
        bid=str(x.get("bid") or x.get("bookId") or "").strip()
        title=str(x.get("bName") or x.get("bookName") or "").strip()
        if not bid.isdigit() or not title: continue
        out.append({
          "platform":"qidian","work_id":bid,"title":title,
          "author":x.get("bAuth") or x.get("author"),
          "category":x.get("cat"),"subcategory":x.get("subCat"),
          "status":x.get("state"),"word_count_raw":x.get("cnt"),
          "description":x.get("desc"),"audience_channel":gender,
          "page_num":page,"row_on_page":pos,
          "work_url":f"https://m.qidian.com/book/{bid}/",
          "source_type":"official_mobile_category_library",
          "raw_record":x,
        })
    meta={
      "code":payload.get("code"),"msg":payload.get("msg"),
      "total":data.get("total"),"pageNum":data.get("pageNum"),
      "pageSize":data.get("pageSize"),"isLast":data.get("isLast"),
      "records":len(rows),
    }
    return out,meta


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--gender",choices=["male","female"],default="male")
    ap.add_argument("--start-page",type=int,default=1)
    ap.add_argument("--pages",type=int,default=2)
    ap.add_argument("--delay",type=float,default=3.0)
    a=ap.parse_args()
    if a.start_page<1 or not 1<=a.pages<=200: ap.error("invalid page bounds")

    out=Path(a.out); out.mkdir(parents=True,exist_ok=False)
    records=[]; logs=[]; pages=[]; seen=set(); blocked=False
    try:
        opener,csrf=session()
    except Exception as e:
        opener=None; csrf=""
        logs.append({"kind":"session_prime","error":repr(e),"started_at":utcnow()})
    for page in range(a.start_page,a.start_page+a.pages):
        params={"catId":"-1","pageNum":str(page),"gender":a.gender}
        if csrf: params["_csrfToken"]=csrf
        url=BASE+"?"+urlencode(params)
        referer="https://m.qidian.com/category/"
        log={"url":url,"gender":a.gender,"page":page,"started_at":utcnow()}
        try:
            if opener is None: raise ValueError("session_prime_failed")
            status,ctype,body,obj=fetch_json(opener,url,referer)
            rows,meta=parse(obj,a.gender,page)
            log.update(status=status,content_type=ctype,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),api_code=meta.get("code"),records=len(rows))
            pages.append({"gender":a.gender,"page":page,**meta})
            (out/f"{a.gender}_p{page:06}.json").write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
            for r in rows:
                key=(r["audience_channel"],r["work_id"])
                if key in seen: continue
                seen.add(key); records.append(r)
            if meta.get("isLast") or not rows:
                logs.append(log); break
        except HTTPError as e:
            log.update(status=e.code,error=repr(e))
            if e.code in BLOCK: blocked=True
        except (URLError,TimeoutError,json.JSONDecodeError,ValueError) as e:
            log["error"]=repr(e)
        logs.append(log)
        if blocked: break
        time.sleep(max(2.0,a.delay))

    with (out/"qidian_catalog_records.jsonl").open("w",encoding="utf-8") as f:
        for r in records: f.write(json.dumps(r,ensure_ascii=False)+"\n")
    (out/"retrieval_log.json").write_text(json.dumps(logs,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={
      "gender":a.gender,"start_page":a.start_page,"requested_pages":a.pages,
      "completed_pages":len(pages),"unique_works":len(records),
      "first_page_meta":pages[0] if pages else None,
      "last_page_meta":pages[-1] if pages else None,
      "blocked_stop":blocked,"csrf_obtained":bool(csrf),"created_at":utcnow(),
      "scope":"official mobile category bibliographic metadata only",
    }
    (out/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))


if __name__=="__main__": main()
