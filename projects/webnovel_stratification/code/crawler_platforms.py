"""Public metadata adapters: one persistent task per page, never chapter prose.

The existing parsers are reused. This layer validates their output, labels date
semantics, and returns newly discovered tasks without doing storage or retries.
"""
from datetime import datetime, timezone
import json
import re
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup

from build_database import unit_number
from collect_catalog import BASE as JJ_BASE, parse_jjwxc
from collect_jjwxc_public_metadata import completion_candidates
from collect_qidian_catalog import BASE as QD_BASE, MALE_CATEGORIES, parse as parse_qd_catalog
from collect_qidian_api_metadata import parse_mobile_book, parse_mobile_catalog
from date_parser_v04 import date_value, parse_jj_detail
from crawler_http import FetchError
from crawler_dates import SCOPE, publication_window

KINDS = {
    "qidian": ["qidian_catalog", "qidian_detail", "qidian_dates", "qidian_chapters"],
    "jjwxc": ["jjwxc_catalog", "jjwxc_detail"],
}
ACTIVE_KINDS = {platform: [kind for kind in kinds if kind != "qidian_chapters"]
                for platform, kinds in KINDS.items()}

JJ_DIMENSIONS = [
    ("yc", [1, 2]), ("xx", [1, 2, 3, 5, 6]), ("isfinish", [1, 2]),
    ("sd", [1, 2, 4, 5]),
    ("lx", [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 16, 17, 20, 18, 19, 21, 22, 23, 24, 25, 27]),
    ("mainview", [1, 2, 3, 4, 5, 8, 9, 12, 13]),
    ("novelbefavoritedcount", [1, 2, 3, 4, 5, 6]),
]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def task(platform, kind, params, priority=100):
    return dict(platform=platform, kind=kind, params=params, priority=priority)


def initial_catalog_jobs(start_year=2005, end_year=2026):
    for cat in MALE_CATEGORIES:
        yield task("qidian", "qidian_catalog", {"cat": cat, "page": 1}, 50)
    for year in range(start_year, end_year + 1):
        yield task("jjwxc", "jjwxc_catalog", {"year": year, "filters": {}, "depth": 0, "page": 1}, 50)


def detail_jobs(platform, work_id):
    yield task(platform, platform + "_detail", {"work_id": str(work_id)}, 100)
    if platform == "qidian":
        yield task(platform, "qidian_dates", {"work_id": str(work_id)}, 110)


def invalid(message):
    raise FetchError("invalid", message)


def result(url, **meta):
    return {"works": [], "dates": [], "chapters": [], "followups": [],
            "meta": {"source_url": url, "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **meta}}


def check_rows(rows, raw_count=None, *, allow_missing_title=False):
    ids = [str(row.get("work_id", "")) for row in rows]
    if any(not re.fullmatch(r"[0-9]+", wid) for wid in ids):
        invalid("invalid_work_id")
    if len(set(ids)) != len(ids):
        invalid("duplicate_id_inside_page")
    if raw_count is not None and raw_count != len(rows):
        invalid("unparsed_catalog_rows")
    if not allow_missing_title and any(not row.get("title") for row in rows):
        invalid("catalog_title_missing")
    return ids


def qidian_catalog(client, params):
    cat, page = str(params["cat"]), int(params["page"])
    if not client.can_fetch(QD_BASE):
        # The public HTML route has its own source and coverage. Never request a
        # robots-denied API or claim its hidden pagination was collected.
        from crawler_qidian_html import parse_qidian_category_html
        if page != 1 or any(params.get(key) for key in ("size", "isfinish")):
            invalid("qidian_api_partition_not_permitted")
        url = f"https://m.qidian.com/category/catid{cat}/"
        response = client.get(url)
        rows, meta = parse_qidian_category_html(response.body, url, cat)
        ids = check_rows(rows)
        partition = {k: v for k, v in params.items() if k != "page"}
        output = result(url, **meta)
        output["meta"].update(page_ids=ids, partition_key=canonical(partition), page=1,
                              coverage="public_html_partial", api_requested=False)
        output["works"] = rows
        for row in rows:
            output["followups"].extend(detail_jobs("qidian", row["work_id"]))
        return output
    if not getattr(client, "qidian_primed", False):
        client.get("https://m.qidian.com/category/male")
        client.qidian_primed = True
    query = {"catId": cat, "pageNum": page, "gender": "male"}
    for name in ("size", "isfinish"):
        if params.get(name):
            query[name] = params[name]
    public_url = QD_BASE + "?" + urlencode(query)
    csrf = client.get_csrf()
    if csrf:
        query["_csrfToken"] = csrf
    response = client.get(QD_BASE + "?" + urlencode(query), accept="application/json",
                          referer=f"https://m.qidian.com/category/catid{cat}/")
    try:
        payload = json.loads(response.body)
    except (ValueError, UnicodeError):
        invalid("qidian_catalog_not_json")
    rows, meta = parse_qd_catalog(payload, "male", cat, page)
    if meta.get("code") != 0:
        invalid("qidian_catalog_api_error")
    if str(meta.get("pageNum")) != str(page):
        invalid("qidian_page_mismatch")
    total, size = meta.get("total"), meta.get("pageSize")
    if not isinstance(total, int) or total < 0 or not isinstance(size, int) or size <= 0:
        invalid("qidian_pagination_unknown")
    ids = check_rows(rows, meta.get("records"))
    if not rows and not (total == 0 and page == 1):
        invalid("qidian_unexpected_empty_page")
    partition = {k: v for k, v in params.items() if k != "page"}
    output = result(public_url, page_ids=ids, partition_key=canonical(partition), page=page,
                    reported_total=total, coverage="leaf", api_meta=meta)
    output["works"] = [{**r, "genre": r.get("category"), "word_count": unit_number(r.get("word_count_raw"))} for r in rows]
    if total >= 10000 and page == 1 and not params.get("size"):
        output["followups"] = [task("qidian", "qidian_catalog", {**params, "size": str(v)}, 55) for v in range(1, 6)]
        output["meta"]["coverage"] = "partitioned_unverified"
    elif total >= 10000 and page == 1 and not params.get("isfinish"):
        output["followups"] = [task("qidian", "qidian_catalog", {**params, "isfinish": str(v)}, 55) for v in (1, 2)]
        output["meta"]["coverage"] = "partitioned_unverified"
    else:
        if total >= 10000:
            output["meta"]["coverage"] = "api_cap_unresolved"
        expected_last = page * size >= total
        if bool(meta.get("isLast")) != expected_last:
            invalid("qidian_end_of_catalog_inconsistent")
        if not expected_last:
            output["followups"].append(task("qidian", "qidian_catalog", {**params, "page": page + 1}, 60))
        if total == 0:
            output["meta"]["coverage"] = "complete_empty"
    for row in rows:
        output["followups"].extend(detail_jobs("qidian", row["work_id"]))
    return output


def jjwxc_catalog(client, params):
    year, page, depth = int(params["year"]), int(params["page"]), int(params.get("depth", 0))
    filters = params.get("filters", {})
    query = {"version": 1, "fw1": 1, f"fbsj{year}": year, "sortType": 3, **filters, "page": page}
    url = JJ_BASE + "?" + urlencode(query)
    response = client.get(url)
    observed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows, meta = parse_jjwxc(response.body, url, observed)
    if meta.get("current_page") != page or not isinstance(meta.get("total_pages"), int):
        invalid("jjwxc_pagination_unknown_or_wrong")
    total = meta["total_pages"]
    if any(r.get("declared_pub_year") != year for r in rows):
        invalid("jjwxc_year_filter_not_applied")
    if not rows and total not in (0, 1):
        invalid("jjwxc_unexpected_empty_page")
    if not rows and not re.search(r"(?:没有|暂无|未找到).{0,12}(?:作品|文章|记录)|共\s*0\s*页", BeautifulSoup(response.body, "html.parser").get_text(" ", strip=True)):
        invalid("jjwxc_empty_not_explicit")
    # Official catalog anchors can contain whitespace-only titles. Preserve the
    # verified ID and explicit missingness instead of losing the whole page.
    for row in rows:
        row["title_missing_from_catalog"] = not bool(row.get("title"))
        if row["title_missing_from_catalog"]:
            row["title"] = None
    ids = check_rows(rows, allow_missing_title=True)
    partition = {k: v for k, v in params.items() if k != "page"}
    output = result(url, page_ids=ids, partition_key=canonical(partition), page=page,
                    reported_pages=total, coverage="leaf", requested_year=year,
                    requested_filters=filters, filter_exhaustiveness="not_established")
    output["works"] = [{**r, "genre": r.get("genre_raw"), "catalog_pub_year": r.get("declared_pub_year")} for r in rows]
    for row in rows:
        if row.get("date_raw"):
            output["dates"].append({"work_id": row["work_id"], "role": "catalog_publication",
                                    "value": row["date_raw"], "basis": "official_catalog_label"})
    if page == 1 and total > 10:
        soup = BeautifulSoup(response.body, "html.parser")
        while depth < len(JJ_DIMENSIONS):
            name, values = JJ_DIMENSIONS[depth]
            depth += 1
            children = []
            for value in values:
                key = name if name == "isfinish" else name + str(value)
                # Use only filter options actually advertised by the returned form.
                present = soup.find("input", attrs={"name": key, "value": str(value)})
                if name == "isfinish":
                    select = soup.find("select", attrs={"name": name})
                    present = present or (select and select.find("option", attrs={"value": str(value)}))
                if present:
                    children.append(task("jjwxc", "jjwxc_catalog", {**params, "depth": depth, "filters": {**filters, key: value}}, 55))
            if children:
                output["followups"].extend(children)
                output["meta"]["coverage"] = "partitioned_unverified"
                break
        else:
            output["meta"]["coverage"] = "page_limit_unresolved"
    elif page < min(total, 10):
        if not meta.get("next_url"):
            invalid("jjwxc_next_link_missing")
        next_query = parse_qs(urlparse(meta["next_url"]).query)
        if next_query.get("page") != [str(page + 1)]:
            invalid("jjwxc_next_page_mismatch")
        output["followups"].append(task("jjwxc", "jjwxc_catalog", {**params, "page": page + 1}, 60))
    if total == 0 or not rows:
        output["meta"]["coverage"] = "complete_empty"
    for row in rows:
        output["followups"].extend(detail_jobs("jjwxc", row["work_id"]))
    return output


def qidian_metadata_body(body, wid):
    """Make the legacy parser consume the same Book whose identity was checked."""
    soup = BeautifulSoup(body, "html.parser")
    books = []
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            value = json.loads(node.string or node.get_text())
        except ValueError:
            continue
        objects = value if isinstance(value, list) else [value, *(value.get("@graph", []) if isinstance(value, dict) else [])]
        for obj in objects:
            if isinstance(obj, dict) and obj.get("@type") == "Book":
                books.append(obj)
    canonical_ids = []
    for node in soup.select('link[rel="canonical"],meta[property="og:url"]'):
        url = urlparse(urljoin(f"https://m.qidian.com/book/{wid}/", node.get("href") or node.get("content") or ""))
        match = re.fullmatch(r"/(?:book|info)/([0-9]+)/?", url.path)
        if url.hostname in {"m.qidian.com", "www.qidian.com", "book.qidian.com"} and match:
            canonical_ids.append(match.group(1))
    if canonical_ids and any(value != wid for value in canonical_ids):
        invalid("qidian_canonical_identity_mismatch")
    matching = [book for book in books if isinstance(book.get("identifier"), dict)
                and str(book["identifier"].get("value")) == wid]
    if matching:
        selected = matching[0]
        # Multiple definitions for the requested ID may disagree; quarantine
        # instead of letting document order choose the research metadata.
        fields = ("name", "author", "datePublished", "dateModified", "genre")
        if any(any(book.get(key) != selected.get(key) for key in fields) for book in matching[1:]):
            invalid("qidian_conflicting_book_jsonld")
    elif wid in canonical_ids:
        if len(books) > 1 or any(book.get("identifier") for book in books):
            invalid("qidian_ambiguous_book_jsonld")
        selected = books[0] if books else None
    else:
        invalid("qidian_work_identity_unverified")
    for node in soup.find_all("script", attrs={"type": "application/ld+json"}):
        node.decompose()
    if selected is not None:
        node = soup.new_tag("script", attrs={"type": "application/ld+json"})
        node.string = json.dumps(selected, ensure_ascii=False)
        soup.append(node)
    return soup.encode("utf-8")


def qidian_detail(client, params):
    wid = str(params["work_id"])
    url = f"https://m.qidian.com/book/{wid}/"
    response = client.get(url)
    info = parse_mobile_book(qidian_metadata_body(response.body, wid), wid, url)
    info["html_bytes_transient"] = len(response.body)
    if not info.get("title") or not info.get("author"):
        invalid("qidian_work_metadata_missing")
    output = result(url)
    output["works"] = [{**info, "work_id": wid, "genre": info.get("category"), "work_url": url}]
    for field, role, basis in [("date_published", "platform_publication", "schema.org_Book_datePublished"),
                              ("date_modified", "last_update", "schema.org_Book_dateModified"),
                              ("update_time", "last_update", "official_update_time")]:
        value = info.get(field)
        if value and date_value(value):
            output["dates"].append({"work_id": wid, "role": role, "value": value, "basis": basis})
    return output


def qidian_chapters(client, params):
    wid = str(params["work_id"])
    url = f"https://m.qidian.com/book/{wid}/catalog/"
    response = client.get(url)
    rows = parse_mobile_catalog(response.body, wid, url)
    if not rows:
        invalid("qidian_no_validated_chapter_catalog")
    output = result(url, chapter_count_observed=len(rows), catalog_completeness="not_independently_verified")
    seen = set()
    for row in rows:
        cid = str(row.get("chapter_id") or "")
        chapter_url = urlparse(row.get("url") or "")
        expected_path = rf"/(?:chapter|read)/{re.escape(wid)}/{re.escape(cid)}/?"
        if (not cid.isdigit() or cid in seen or chapter_url.hostname != "m.qidian.com"
                or not re.fullmatch(expected_path, chapter_url.path)):
            invalid("qidian_chapter_identity_invalid")
        seen.add(cid)
        # Catalog display times are updates, not proof of original publication.
        output["chapters"].append({**row, "work_id": wid, "chapter_id": cid,
                                   "chapter_url": row.get("url"), "publication_date": None,
                                   "update_date": row.get("display_time"),
                                   "date_semantics": "catalog_update_only"})
    return output


def qidian_dates(client, params):
    # The public catalog request supplies boundary evidence; no chapter body is
    # requested, and its displayed update dates are never publication dates.
    parsed = qidian_chapters(client, params)
    window, dates = publication_window(str(params["work_id"]), parsed["chapters"])
    output = result(parsed["meta"]["source_url"], publication_window=window)
    output["works"] = [{"work_id": str(params["work_id"]), "publication_window": window}]
    output["dates"] = dates
    return output


def _jjwxc_lock_reason(body, soup):
    """Recognize the observed official lock notice, not missing metadata alone."""
    if soup.find("div", id="lockpage") is None:
        return False
    if soup.select('[itemprop="articleSection"], [itemprop="author"], tr[itemprop="chapter"], '
                   'link[rel="canonical"], meta[property="og:url"]'):
        return False
    robots = soup.find("meta", attrs={"name": "robots"})
    if robots is None or not {"noindex", "nofollow"}.issubset(
            re.split(r"[\s,]+", str(robots.get("content", "")).lower())):
        return False
    # The small lock template has no charset declaration. Its GBK bytes can be
    # mistaken for a Western encoding by BeautifulSoup; decode only this notice
    # strictly, without altering how normal work pages establish their identity.
    for encoding in ("utf-8", "gb18030"):
        try:
            notice_soup = BeautifulSoup(body.decode(encoding), "html.parser")
        except UnicodeDecodeError:
            continue
        notice = notice_soup.select_one("div#lockpage > p")
        text = re.sub(r"\s+", "", notice.get_text()) if notice else ""
        if re.fullmatch(r"非常抱歉[，,]相关内容已被作者自行锁定[。.!！]?", text):
            return "jjwxc_author_locked"
        if text == "非常抱歉，相关内容因出版、修改或者存在色情、有害、原创违规、侵权等原因而被网站管理员锁定或删除。":
            return "jjwxc_admin_locked_or_deleted"
    return None


def jjwxc_detail(client, params, *, retain_chapters=True):
    wid = str(params["work_id"])
    url = "https://www.jjwxc.net/onebook.php?novelid=" + wid
    response = client.get(url)
    soup = BeautifulSoup(response.body, "html.parser")
    lock_reason = _jjwxc_lock_reason(response.body, soup)
    if lock_reason:
        received = urlparse(getattr(response, "url", ""))
        if (received.scheme != "https" or received.hostname != "www.jjwxc.net"
                or received.path != "/onebook.php" or parse_qs(received.query) != {"novelid": [wid]}):
            invalid("jjwxc_unavailable_page_identity_mismatch")
        raise FetchError("gone", lock_reason)
    # Public work pages contain VIP chapter references and separate purchase
    # action links. Keep the references as metadata but never request either.
    # Removing only purchase hyperlinks also prevents the legacy parser from
    # accidentally selecting a purchase action as a chapter's identity.
    for node in soup.find_all("a"):
        rel = node.get("rel")
        raw = node.get("href") or (" ".join(rel) if isinstance(rel, list) else rel) or ""
        target = urlparse(urljoin(url, raw))
        if (target.hostname, target.path) == ("my.jjwxc.net", "/backend/buynovel.php"):
            node.unwrap()
    parsed = parse_jj_detail(soup.encode("utf-8"), wid, url)
    title_node = soup.select_one('[itemprop="articleSection"]')
    blank_title = title_node is not None and not title_node.get_text(strip=True)
    if (not parsed.get("title") and not blank_title) or not parsed.get("author"):
        invalid("jjwxc_work_metadata_missing")
    chapter_references = {("www.jjwxc.net", "/onebook.php"), ("my.jjwxc.net", "/onebook_vip.php")}
    canonical_identity = False
    for node in soup.select('link[rel="canonical"],meta[property="og:url"]'):
        target = urlparse(urljoin(url, node.get("href") or node.get("content") or ""))
        query = parse_qs(target.query)
        if target.hostname == "www.jjwxc.net" and target.path == "/onebook.php" and "novelid" in query:
            if query["novelid"] != [wid]:
                invalid("jjwxc_canonical_identity_mismatch")
            canonical_identity = True
    # The old parser can retain an itemprop=chapter row with no usable link.
    # Inspect explicit links first so a mismatching book is not hidden by that
    # fallback. Chapter URLs are metadata only and are never requested.
    linked_identity = False
    for tr in soup.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 3 or not cells[0].get_text(strip=True).isdigit():
            continue
        for node in tr.find_all("a"):
            rel = node.get("rel")
            raw = node.get("href") or (" ".join(rel) if isinstance(rel, list) else rel) or ""
            target = urlparse(urljoin(url, raw))
            query = parse_qs(target.query)
            if "chapterid" not in query:
                continue
            if (target.scheme not in {"http", "https"} or (target.hostname, target.path) not in chapter_references
                    or target.username or target.password or query.get("novelid") != [wid]
                    or len(query["chapterid"]) != 1 or not re.fullmatch(r"[0-9]+", query["chapterid"][0])):
                invalid("jjwxc_chapter_identity_mismatch")
            linked_identity = True
    # Some public work pages retain metadata but expose no chapter links.
    # Require two dedicated work widgets to agree, plus the exact response URL;
    # arbitrary recommendations or a requested URL alone cannot prove identity.
    click_ids = [node.get_text(strip=True) for node in soup.select("div#clickNovelid")]
    review_ids = [str(node.get("data-novelid", "")) for node in soup.select("div#novelreview_div")]
    if any(value != wid for value in click_ids + review_ids):
        invalid("jjwxc_widget_identity_mismatch")
    received = urlparse(getattr(response, "url", ""))
    controls = soup.select("span.uninterested-author[data-novelid]")
    control_identity = bool(controls) and all(
        node.get("data-novelid") == wid
        and re.sub(r"\s+", " ", str(node.get("data-novelname", ""))).strip() == (parsed["title"] or "")
        and re.sub(r"\s+", " ", str(node.get("data-authorname", ""))).strip() == parsed["author"]
        for node in controls)
    # All-locked works may omit the review widget. Their dedicated work control
    # carries ID, title and author, independently of the click counter.
    widget_identity = (click_ids == [wid] and (review_ids == [wid] or (not review_ids and control_identity))
                       and received.scheme == "https" and received.hostname == "www.jjwxc.net"
                       and received.path == "/onebook.php" and parse_qs(received.query) == {"novelid": [wid]})
    if not canonical_identity and not linked_identity and not widget_identity:
        invalid("jjwxc_work_identity_unverified")
    if blank_title and not (widget_identity and control_identity):
        invalid("jjwxc_blank_title_identity_unverified")
    chapters, unverified, seen = [], [], set()
    for chapter in parsed["chapters"]:
        if not chapter.get("chapter_url"):
            unverified.append(chapter)
            continue
        target = urlparse(chapter["chapter_url"])
        query = parse_qs(target.query)
        cid = chapter.get("chapter_id")
        if (target.scheme not in {"http", "https"} or (target.hostname, target.path) not in chapter_references
                or target.username or target.password or query.get("novelid") != [wid]
                or not re.fullmatch(r"[0-9]+", str(cid or "")) or query.get("chapterid") != [cid]
                or cid in seen):
            invalid("jjwxc_chapter_identity_mismatch")
        seen.add(cid)
        chapters.append(chapter)
    output = result(url, chapter_count_observed=len(chapters),
                    **({"unverified_chapter_rows": unverified} if retain_chapters else
                       {"unverified_chapter_row_count": len(unverified)}),
                    catalog_completeness="not_independently_verified")
    output["works"] = [{"work_id": wid, "title": parsed["title"] or None, "title_missing_from_detail": blank_title, "author": parsed["author"],
                         "status": parsed.get("status"), "work_url": url, "metadata_fields": parsed.get("metadata_fields")}]
    if not retain_chapters:
        window, dates = publication_window(wid, chapters, parsed.get("status"))
        output["meta"]["publication_window"] = window
        output["works"][0]["publication_window"] = window
        output["dates"] = dates
        return output
    for chapter in chapters:
        output["chapters"].append({**chapter, "work_id": wid,
                                   "chapter_id": chapter["chapter_id"],
                                   "publication_date": chapter.get("publish_time_as_supplied"),
                                   "update_date": chapter.get("update_time_as_supplied"),
                                   "is_vip": chapter.get("is_vip_as_supplied")})
    if chapters:
        dates = [(chapters[0], "publish_time_as_supplied", "first_observed_chapter_publication"),
                 (chapters[-1], "publish_time_as_supplied", "last_observed_chapter_publication"),
                 (chapters[-1], "update_time_as_supplied", "last_observed_chapter_update")]
        if chapters[0]["chapter_number_raw"] == "1":
            dates.append((chapters[0], "publish_time_as_supplied", "first_chapter_publication"))
        for chapter, field, role in dates:
            if chapter.get(field):
                output["dates"].append({"work_id": wid, "role": role, "value": chapter[field], "basis": "official_" + field})
    candidates = completion_candidates({**parsed, "chapters": chapters})
    if retain_chapters:
        output["meta"]["completion_candidates"] = candidates
    rank = {"all_text_end_marker_update": 3, "main_story_end_marker_update": 2, "ending_marker_update": 1}
    if candidates:
        best = max(candidates, key=lambda c: (rank.get(c.get("role"), 0), c.get("basis") == "explicit_chapter_publication"))
        if best.get("date_candidate"):
            output["dates"].append({"work_id": wid, "role": "completion_candidate", "value": best["date_candidate"],
                                    "basis": best["role"] + ":" + best["basis"]})
    return output


ADAPTERS = {name: globals()[name] for kinds in KINDS.values() for name in kinds}


def run_task(client, job):
    if job["kind"] not in KINDS.get(job["platform"], []):
        invalid("task_platform_mismatch")
    if job["kind"] not in ACTIVE_KINDS[job["platform"]]:
        invalid("task_excluded_by_collection_scope")
    if job["kind"] == "jjwxc_detail":
        output = jjwxc_detail(client, job["params"], retain_chapters=False)
    else:
        output = ADAPTERS[job["kind"]](client, job["params"])
    output["meta"]["collection_scope"] = SCOPE
    return output
