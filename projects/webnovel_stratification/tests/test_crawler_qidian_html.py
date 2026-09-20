"""Offline validation of the permitted public category HTML first page."""
import copy
import html
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from crawler_qidian_html import (
    CategoryHTMLValidationError, first_page_url, parse_qidian_category_html,
    qidian_category_html_result,
)


URL = "https://m.qidian.com/category/catid10/"


def record(wid, title="示例作品", count="531.57万字"):
    return {"bid": wid, "bName": title, "bAuth": "示例作者", "catId": 10,
            "cat": "悬疑灵异", "state": "完结", "cnt": count, "desc": "公开简介"}


def fixture(records=None, change=None, visible=None, recommendation=True):
    records = [record(123), record(456, "另一作品", "900字")] if records is None else records
    listing = {"total": len(records), "isLast": 1, "records": records,
               "keyState": 0, "pageSize": max(len(records), 1), "pageNum": 1, "pageMax": 50}
    context = {"_pageId": "/src/pages/categoryDetail/index", "hostname": "m.qidian.com",
               "urlPathname": "/category/catid10/", "urlOriginal": "/category/catid10/",
               "routeParams": {"catid": "10", "otherParams": "", "gender": "male"},
               "pageProps": {"pageData": {"catId": 10, "gender": "male", "pageCat": "悬疑灵异", "list": listing,
                                            "selected": [{"bid": 999, "bName": "推荐作品"}]}}}
    if change:
        change(context)
    rendered = records if visible is None else visible
    cards = []
    for row in rendered:
        text = lambda key: html.escape(str(row[key]))
        cards.append('<div class="y-list__item"><a data-bid="' + text("bid") + '" href="//m.qidian.com/book/' + text("bid") + '/"><h2>' + text("bName") + '</h2>'
                     + "".join("<p>" + text(key) + "</p>" for key in ("bAuth", "cat", "state", "cnt")) + "</a></div>")
    extra = '<aside><a data-bid="999" href="//m.qidian.com/book/999/"><h2>推荐作品</h2></a></aside>' if recommendation else ""
    return ("<html><body>" + extra + "".join(cards) + '<script id="vite-plugin-ssr_pageContext" type="application/json">'
            + json.dumps({"pageContext": context}, ensure_ascii=False) + "</script></body></html>").encode()


class PublicCategoryHTMLTests(unittest.TestCase):
    def test_reads_explicit_list_and_excludes_recommendations(self):
        rows, meta = parse_qidian_category_html(fixture(), URL, 10)
        self.assertEqual([r["work_id"] for r in rows], ["123", "456"])
        self.assertEqual((rows[0]["title"], rows[0]["author"], rows[0]["status"]), ("示例作品", "示例作者", "完结"))
        self.assertEqual(rows[0]["word_count"], 5315700)
        self.assertTrue(rows[0]["word_count_is_approximate"])
        self.assertEqual(rows[1]["word_count"], 900)
        self.assertFalse(rows[1]["word_count_is_approximate"])
        self.assertEqual(meta["coverage"], "public_html_partial")
        self.assertTrue(meta["reported_total_is_capped_or_unverified"])

    def test_first_page_only_and_no_hidden_url_generation(self):
        self.assertEqual(first_page_url("10"), URL)
        for url in (URL + "?page=2", URL + "page2/", "https://m.qidian.com/webcommon/category/list"):
            with self.subTest(url=url), self.assertRaisesRegex(CategoryHTMLValidationError, "first_page"):
                parse_qidian_category_html(fixture(), url, 10)
        changed = lambda c: c["pageProps"]["pageData"]["list"].update(pageNum=2)
        with self.assertRaisesRegex(CategoryHTMLValidationError, "metadata_invalid"):
            parse_qidian_category_html(fixture(change=changed), URL, 10)

    def test_category_identity_must_match_requested_page(self):
        changes = [lambda c: c["pageProps"]["pageData"].update(catId=21),
                   lambda c: c["routeParams"].update(catid="21"),
                   lambda c: c.update(urlOriginal="/category/catid10/?page=2"),
                   lambda c: c.update(_pageId="/src/pages/home/index")]
        for change in changes:
            with self.subTest(change=change), self.assertRaisesRegex(CategoryHTMLValidationError, "identity_or_first_page"):
                parse_qidian_category_html(fixture(change=change), URL, 10)

    def test_bad_list_metadata_is_rejected(self):
        for patch in ({"records": None}, {"pageSize": 0}, {"total": -1}, {"total": "2"}, {"pageNum": True}, {"isLast": None}, {"total": 10000, "pageSize": 20}):
            with self.subTest(patch=patch), self.assertRaises(CategoryHTMLValidationError):
                parse_qidian_category_html(fixture(change=lambda c: c["pageProps"]["pageData"]["list"].update(patch)), URL, 10)

    def test_duplicate_or_nonnumeric_book_ids_are_rejected(self):
        for rows in ([record(123), record(123)], [record("１２３")], [record("12evil")], [record(True)]):
            with self.subTest(rows=rows), self.assertRaises(CategoryHTMLValidationError):
                parse_qidian_category_html(fixture(records=rows), URL, 10)

    def test_visible_fields_and_order_must_agree_with_state(self):
        rows = [record(123), record(456, "另一作品")]
        for field in ("bName", "bAuth", "cat", "state", "cnt"):
            changed = copy.deepcopy(rows)
            changed[0][field] = "不同文字"
            with self.subTest(field=field), self.assertRaises(CategoryHTMLValidationError):
                parse_qidian_category_html(fixture(records=rows, visible=changed), URL, 10)
        with self.assertRaisesRegex(CategoryHTMLValidationError, "identity_mismatch"):
            parse_qidian_category_html(fixture(records=rows, visible=list(reversed(rows))), URL, 10)

    def test_unknown_missing_or_fractional_counts_are_rejected(self):
        for count in ("约50万字", "暂未提供", "", "0.5字", None):
            with self.subTest(count=count), self.assertRaises(CategoryHTMLValidationError):
                parse_qidian_category_html(fixture(records=[record(123, count=count)]), URL, 10)

    def test_valid_empty_page_still_does_not_claim_global_coverage(self):
        rows, meta = parse_qidian_category_html(fixture(records=[]), URL, 10)
        self.assertEqual(rows, [])
        self.assertEqual(meta["coverage"], "public_html_partial")
        self.assertEqual(meta["reported_total"], 0)

    def test_result_schedules_only_detail_and_chapter_metadata(self):
        output = qidian_category_html_result(fixture(), URL, 10, observed_at="2026-09-20T01:00:00Z")
        self.assertEqual(len(output["followups"]), 4)
        self.assertEqual({j["kind"] for j in output["followups"]}, {"qidian_detail", "qidian_chapters"})
        self.assertTrue(all(set(j["params"]) == {"work_id"} for j in output["followups"]))
        self.assertEqual(output["meta"]["observed_at"], "2026-09-20T01:00:00Z")
        self.assertEqual(output["dates"], [])

    def test_real_saved_category_page(self):
        path = ROOT / "data/raw/crawler_diagnostics_20260920/qidian_category_catid10.html"
        if not path.is_file():
            self.skipTest("Saved public first-page diagnostic is not present")
        rows, meta = parse_qidian_category_html(path.read_bytes(), URL, 10)
        self.assertEqual(len(rows), 20)
        self.assertEqual((rows[0]["work_id"], rows[0]["title"], rows[0]["author"]), ("1012584111", "神秘复苏", "佛前献花"))
        self.assertEqual(rows[0]["word_count"], 5315700)
        self.assertEqual(rows[-1]["work_id"], "68223")
        self.assertNotIn("1050428284", {r["work_id"] for r in rows})
        self.assertEqual(meta["reported_total"], 10000)
        self.assertEqual(meta["coverage"], "public_html_partial")


if __name__ == "__main__":
    unittest.main(verbosity=2)
