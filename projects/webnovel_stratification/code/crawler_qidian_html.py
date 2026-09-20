"""Parse the public Qidian category HTML first page, without API requests.

Only the explicit server-rendered category list is accepted. Recommendation
carousels are excluded, and its public JSON state must agree with the visible
list. Reported totals are retained as unverified metadata, never as coverage.
This module performs no network access and never generates pagination tasks.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup


class CategoryHTMLValidationError(ValueError):
    pass


def _invalid(message):
    raise CategoryHTMLValidationError(message)


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        _invalid("missing_or_invalid_" + field)
    return " ".join(value.split())


def _positive_id(value, field):
    if isinstance(value, bool) or not re.fullmatch(r"[1-9][0-9]*", str(value)):
        _invalid("invalid_" + field)
    return str(value)


def first_page_url(category_id):
    return "https://m.qidian.com/category/catid" + _positive_id(category_id, "category_id") + "/"


def _word_count(value):
    raw = _text(value, "word_count")
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(万|亿)?字", raw)
    if match is None:
        _invalid("invalid_display_word_count")
    try:
        count = Decimal(match[1]) * {None: 1, "万": 10000, "亿": 100000000}[match[2]]
    except InvalidOperation:
        _invalid("invalid_display_word_count")
    if count != count.to_integral_value():
        _invalid("fractional_word_count")
    return int(count), raw, match[2] is not None


def _page_state(soup, category_id):
    nodes = soup.find_all("script", id="vite-plugin-ssr_pageContext", type="application/json")
    if len(nodes) != 1:
        _invalid("category_page_state_missing_or_ambiguous")
    try:
        context = json.loads(nodes[0].string or nodes[0].get_text())["pageContext"]
        data = context["pageProps"]["pageData"]
        listing = data["list"]
        route = context["routeParams"]
    except (ValueError, KeyError, TypeError):
        _invalid("category_page_state_invalid")
    if not all(isinstance(value, dict) for value in (context, data, listing, route)):
        _invalid("category_page_state_invalid")
    expected_path = "/category/catid" + category_id + "/"
    if (context.get("_pageId") != "/src/pages/categoryDetail/index"
            or context.get("hostname") != "m.qidian.com"
            or context.get("urlPathname") != expected_path
            or context.get("urlOriginal") != expected_path
            or str(route.get("catid")) != category_id
            or str(data.get("catId")) != category_id
            or route.get("otherParams") not in (None, "")
            or route.get("gender") != "male" or data.get("gender") != "male"):
        _invalid("category_identity_or_first_page_unverified")
    records = listing.get("records")
    total, size, page = listing.get("total"), listing.get("pageSize"), listing.get("pageNum")
    if (not isinstance(records, list) or type(total) is not int or total < 0
            or type(size) is not int or size <= 0 or type(page) is not int or page != 1
            or len(records) != min(size, total)):
        _invalid("category_list_metadata_invalid")
    if listing.get("isLast") not in (0, 1, False, True):
        _invalid("category_list_end_flag_invalid")
    return data, listing, records


def _visible_items(soup, source_url):
    items = []
    for container in soup.select(".y-list__item"):
        anchors = container.select("a[data-bid][href]")
        if len(anchors) != 1:
            _invalid("visible_category_item_ambiguous")
        anchor = anchors[0]
        wid = _positive_id(anchor.get("data-bid"), "visible_work_id")
        url = urljoin(source_url, anchor["href"])
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.hostname != "m.qidian.com"
                or parsed.path != "/book/" + wid + "/" or parsed.query or parsed.fragment):
            _invalid("visible_book_link_identity_mismatch")
        headings = anchor.find_all("h2")
        if len(headings) != 1:
            _invalid("visible_category_title_missing_or_ambiguous")
        items.append({"work_id": wid, "title": _text(headings[0].get_text(" ", strip=True), "visible_title"),
                      "paragraphs": {" ".join(node.get_text(" ", strip=True).split()) for node in anchor.find_all("p")},
                      "work_url": url})
    return items


def parse_qidian_category_html(body, source_url, category_id):
    """Return (works, meta) from one explicitly identified public first page.

    Validation errors are ValueError subclasses, for the caller's invalid-result
    handling. Do not fall back to generic links or other embedded recommendations.
    """
    category_id = _positive_id(category_id, "category_id")
    if source_url != first_page_url(category_id):
        _invalid("only_public_category_first_page_is_supported")
    soup = BeautifulSoup(body, "html.parser")
    data, listing, records = _page_state(soup, category_id)
    visible = _visible_items(soup, source_url)
    if len(visible) != len(records):
        _invalid("visible_and_state_list_lengths_differ")
    works, seen = [], set()
    for position, (record, rendered) in enumerate(zip(records, visible), 1):
        if not isinstance(record, dict):
            _invalid("invalid_category_record")
        wid = _positive_id(record.get("bid"), "work_id")
        if wid in seen:
            _invalid("duplicate_work_id_in_category_list")
        seen.add(wid)
        if wid != rendered["work_id"] or str(record.get("catId")) != category_id:
            _invalid("category_record_identity_mismatch")
        title = _text(record.get("bName"), "title")
        author = _text(record.get("bAuth"), "author")
        status = _text(record.get("state"), "status")
        genre = _text(record.get("cat"), "category")
        count, raw_count, approximate = _word_count(record.get("cnt"))
        if title != rendered["title"] or not {author, status, genre, raw_count}.issubset(rendered["paragraphs"]):
            _invalid("visible_and_state_book_fields_differ")
        works.append({
            "platform": "qidian", "work_id": wid, "title": title, "author": author,
            "genre": genre, "status": status, "word_count": count, "word_count_raw": raw_count,
            "word_count_is_approximate": approximate,
            "word_count_basis": "displayed_count_scaled" if approximate else "displayed_count",
            "work_url": rendered["work_url"], "category_id": category_id,
            "row_on_page": position, "selection_method": "public_category_first_page",
            "raw_metadata": {key: record[key] for key in ("bid", "bName", "bAuth", "catId", "cat", "state", "cnt", "desc") if key in record},
        })
    return works, {
        "source_url": source_url, "source_kind": "qidian_public_category_html",
        "coverage": "public_html_partial", "page": 1,
        "partition_key": json.dumps({"category_id": category_id, "transport": "public_html"}, sort_keys=True, separators=(",", ":")),
        "page_ids": [row["work_id"] for row in works], "category_id": category_id,
        "category_name": data.get("pageCat"), "record_count": len(works),
        "reported_total": listing["total"], "reported_page_size": listing["pageSize"],
        "reported_is_last": listing["isLast"], "reported_page_max": listing.get("pageMax"),
        "reported_total_is_capped_or_unverified": True,
        "state_location": "pageContext.pageProps.pageData.list.records",
        "validation": "list_state_matches_visible_book_ids_and_fields",
        "scope": "public category HTML first page only; full catalog coverage not established",
    }


def qidian_category_html_result(body, source_url, category_id, observed_at=None):
    """Build the Store result contract; only detail/chapter tasks are scheduled."""
    works, meta = parse_qidian_category_html(body, source_url, category_id)
    meta["observed_at"] = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    followups = [
        {"platform": "qidian", "kind": kind, "params": {"work_id": row["work_id"]}, "priority": priority}
        for row in works for kind, priority in (("qidian_detail", 100), ("qidian_chapters", 110))
    ]
    return {"works": works, "dates": [], "chapters": [], "followups": followups, "meta": meta}
