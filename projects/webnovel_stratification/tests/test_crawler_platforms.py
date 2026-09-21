import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from crawler_http import FetchError
from crawler_platforms import qidian_catalog, jjwxc_catalog, qidian_detail, qidian_chapters, jjwxc_detail, run_task


class Client:
    qidian_primed = True

    def __init__(self, body):
        self.body = body.encode() if isinstance(body, str) else body
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return SimpleNamespace(body=self.body, status=200, content_type="text/html", url=url)

    def get_csrf(self):
        return "ephemeral-test-value"

    def can_fetch(self, url):
        return True


def qd(total=1, page=1, code=0, records=None, is_last=1):
    return json.dumps({"code": code, "data": {"total": total, "pageNum": page, "pageSize": 20,
                        "isLast": is_last, "records": records if records is not None else [{"bid": 123,
                        "bName": "示例", "bAuth": "作者", "cnt": "1.25万字"}]}})


def jj(year=2010, current=1, total=2):
    return f'''<html><input name="fbsj2010" value="2010"><input name="yc1" value="1">
        <input name="yc2" value="2"><p>共{total}页 当前为第{current}页</p>
        <table class="cytable"><tr><td><a href="?authorid=5">作者</a></td>
        <td><a href="onebook.php?novelid=321">作品</a></td><td>原创-言情-近代现代-爱情</td>
        <td>连载</td><td>1000</td><td>200</td><td>{year}-01-01 00:00:00</td></tr></table>
        <a href="bookbase.php?fbsj2010=2010&amp;page=2">下一页</a></html>'''


class AdapterTests(unittest.TestCase):
    def test_api_failure_is_not_empty_success(self):
        with self.assertRaises(FetchError):
            qidian_catalog(Client(qd(code=500)), {"cat": "21", "page": 1})

    def test_wrong_page_does_not_advance(self):
        with self.assertRaises(FetchError):
            qidian_catalog(Client(qd(page=1)), {"cat": "21", "page": 2})

    def test_capped_partition_splits_without_claiming_full_coverage(self):
        result = qidian_catalog(Client(qd(total=10000, is_last=0)), {"cat": "21", "page": 1})
        children = [j for j in result["followups"] if j["kind"] == "qidian_catalog"]
        self.assertEqual(len(children), 5)
        self.assertEqual(result["meta"]["coverage"], "partitioned_unverified")
        self.assertNotIn("ephemeral-test-value", json.dumps(result))
        self.assertEqual(result["works"][0]["word_count"], 12500)

    def test_unparsed_rows_reject_whole_page(self):
        with self.assertRaises(FetchError):
            qidian_catalog(Client(qd(records=[{"bid": "bad", "bName": "x"}])), {"cat": "21", "page": 1})

    def test_missing_year_filter_rejects_page(self):
        with self.assertRaises(FetchError):
            jjwxc_catalog(Client(jj(year=2020)), {"year": 2010, "page": 1})

    def test_jjwxc_pagination_is_explicit(self):
        result = jjwxc_catalog(Client(jj()), {"year": 2010, "page": 1, "filters": {}, "depth": 0})
        next_page = [j for j in result["followups"] if j["kind"] == "jjwxc_catalog"]
        self.assertEqual(next_page[0]["params"]["page"], 2)
        self.assertEqual(result["dates"][0]["role"], "catalog_publication")

    def test_jjwxc_split_is_durable_child_tasks(self):
        result = jjwxc_catalog(Client(jj(total=40)), {"year": 2010, "page": 1, "filters": {}, "depth": 0})
        children = [j for j in result["followups"] if j["kind"] == "jjwxc_catalog"]
        self.assertEqual([j["params"]["filters"] for j in children], [{"yc1": 1}, {"yc2": 2}])

    def test_wrong_qidian_book_identity_rejected(self):
        body = '<script type="application/ld+json">' + json.dumps({"@type": "Book", "identifier": {"value": "999"}, "name": "错误作品"}) + '</script><h1>错误作品</h1>'
        with self.assertRaises(FetchError):
            qidian_detail(Client(body), {"work_id": "123"})

    def test_qidian_extracts_the_book_that_matched_requested_id(self):
        books = [{"@type": "Book", "name": "Wrong book without ID", "author": {"name": "Wrong author"},
                  "datePublished": "2000-01-01"},
                 {"@type": "Book", "identifier": {"value": "123"}, "name": "Requested book",
                  "author": {"name": "Requested author"}, "datePublished": "2010-01-01"}]
        body = '<script type="application/ld+json">' + json.dumps(books) + '</script>'
        result = qidian_detail(Client(body), {"work_id": "123"})
        self.assertEqual(result["works"][0]["title"], "Requested book")
        self.assertEqual(result["works"][0]["author"], "Requested author")
        self.assertEqual(next(d["value"] for d in result["dates"] if d["role"] == "platform_publication"), "2010-01-01")

    def test_qidian_related_book_cannot_override_conflicting_canonical(self):
        body = '<link rel="canonical" href="https://m.qidian.com/book/999/">'
        body += '<script type="application/ld+json">' + json.dumps({"@type": "Book",
                  "identifier": {"value": "123"}, "name": "Related book", "author": {"name": "A"}}) + '</script>'
        with self.assertRaises(FetchError):
            qidian_detail(Client(body), {"work_id": "123"})

    def test_qidian_conflicting_definitions_for_one_id_are_rejected(self):
        books = [{"@type": "Book", "identifier": {"value": "123"}, "name": name,
                  "author": {"name": "A"}} for name in ("First title", "Other title")]
        body = '<script type="application/ld+json">' + json.dumps(books) + '</script>'
        with self.assertRaises(FetchError):
            qidian_detail(Client(body), {"work_id": "123"})

    def test_qidian_canonical_still_supports_metadata_only_page(self):
        body = '''<link rel="canonical" href="https://www.qidian.com/book/123/">
          <meta property="og:novel:book_name" content="Metadata title">
          <meta property="og:novel:author" content="Metadata author">'''
        result = qidian_detail(Client(body), {"work_id": "123"})
        self.assertEqual(result["works"][0]["title"], "Metadata title")

    def test_chapter_links_are_parsed_but_never_requested(self):
        client = Client('<a href="https://m.qidian.com/chapter/123/456/">第一章 2020-01-01 00:00:00</a>')
        result = qidian_chapters(client, {"work_id": "123"})
        self.assertEqual(client.urls, ['https://m.qidian.com/book/123/catalog/'])
        self.assertIsNone(result["chapters"][0]["publication_date"])
        self.assertEqual(result["chapters"][0]["update_date"], "2020-01-01 00:00:00")

    def test_qidian_endpoint_task_requests_catalog_once_without_chapter_records(self):
        client = Client('<a href="https://m.qidian.com/chapter/123/456/">正文完结 2020-01-01 00:00:00</a>')
        result = run_task(client, {"platform": "qidian", "kind": "qidian_dates", "params": {"work_id": "123"}})
        self.assertEqual(client.urls, ['https://m.qidian.com/book/123/catalog/'])
        self.assertEqual(result["chapters"], [])
        self.assertTrue(all("update" in d["role"] for d in result["dates"]))
        self.assertEqual(result["works"][0]["publication_window"]["main_text_end_candidate"]["chapter_id"], "456")
        self.assertEqual(result["meta"]["collection_scope"], "work_date_endpoints")

    def test_jjwxc_explicit_publication_separate_from_update(self):
        body = '''<span itemprop="articleSection">作品</span><span itemprop="author">作者</span>
        <table><tr itemprop="chapter"><td>1</td><td><a href="onebook.php?novelid=321&amp;chapterid=1">第一章</a></td>
        <td title="章节首发时间：2010-01-01 00:00:00">2020-01-01 00:00:00</td></tr></table>'''
        client = Client(body)
        result = jjwxc_detail(client, {"work_id": "321"})
        self.assertEqual(len(client.urls), 1)
        chapter = result["chapters"][0]
        self.assertEqual(chapter["publication_date"], "2010-01-01 00:00:00")
        self.assertEqual(chapter["update_date"], "2020-01-01 00:00:00")
        self.assertFalse(any(d["role"] == "completion_candidate" for d in result["dates"]))
        roles = {d["role"] for d in result["dates"]}
        self.assertIn("first_chapter_publication", roles)
        self.assertIn("first_observed_chapter_publication", roles)
        self.assertIn("last_observed_chapter_publication", roles)
        self.assertNotIn("last_chapter_publication", roles)

    def test_work_only_task_retains_dates_without_serializing_chapter_rows(self):
        body = '''<span itemprop="articleSection">作品</span><span itemprop="author">作者</span>
        <table><tr itemprop="chapter"><td>1</td><td><a href="onebook.php?novelid=321&amp;chapterid=1">第一章</a></td>
        <td title="章节首发时间：2010-01-01 00:00:00">2020-01-01 00:00:00</td></tr>
        <tr itemprop="chapter"><td>2</td><td>无法核验的章节</td><td>2021-01-01 00:00:00</td></tr></table>'''
        client = Client(body)
        result = run_task(client, {"platform": "jjwxc", "kind": "jjwxc_detail", "params": {"work_id": "321"}})
        self.assertEqual(result["chapters"], [])
        self.assertEqual(len(client.urls), 1)
        self.assertIn("first_chapter_publication", {d["role"] for d in result["dates"]})
        self.assertEqual(result["meta"]["collection_scope"], "work_date_endpoints")
        self.assertEqual(result["meta"]["unverified_chapter_row_count"], 1)
        for value in ("chapter_title", "completion_candidates", "unverified_chapter_rows"):
            self.assertNotIn(value, json.dumps(result))

    def test_retired_chapter_task_makes_no_request(self):
        client = Client("must not fetch")
        with self.assertRaisesRegex(FetchError, "task_excluded_by_collection_scope"):
            run_task(client, {"platform": "qidian", "kind": "qidian_chapters", "params": {"work_id": "1"}})
        self.assertEqual(client.urls, [])

    def test_jjwxc_foreign_book_cannot_pass_fallback_chapter_parser(self):
        body = '''<span itemprop="articleSection">Other book</span><span itemprop="author">Other author</span>
          <table><tr itemprop="chapter"><td>5</td><td><a itemprop="headline"
          href="onebook.php?novelid=999&amp;chapterid=5">Chapter five</a></td>
          <td title="章节首发时间：2011-01-02 03:04:05">2012-01-01 00:00:00</td></tr></table>'''
        with self.assertRaises(FetchError):
            jjwxc_detail(Client(body), {"work_id": "123"})

    def test_jjwxc_external_chapter_host_does_not_establish_identity(self):
        body = '''<span itemprop="articleSection">Book</span><span itemprop="author">Author</span>
          <table><tr itemprop="chapter"><td>1</td><td><a
          href="https://example.invalid/onebook.php?novelid=123&amp;chapterid=1">First chapter</a></td>
          <td title="章节首发时间：2011-01-02 03:04:05">2012-01-01 00:00:00</td></tr></table>'''
        with self.assertRaises(FetchError):
            jjwxc_detail(Client(body), {"work_id": "123"})

    def test_jjwxc_missing_first_chapter_cannot_create_first_publication(self):
        body = '''<span itemprop="articleSection">Book</span><span itemprop="author">Author</span>
          <table><tr itemprop="chapter"><td>1</td><td>Unavailable first chapter</td><td></td></tr>
          <tr itemprop="chapter"><td>5</td><td><a href="onebook.php?novelid=123&amp;chapterid=5">Chapter five</a></td>
          <td title="章节首发时间：2011-01-02 03:04:05">2012-01-01 00:00:00</td></tr></table>'''
        result = jjwxc_detail(Client(body), {"work_id": "123"})
        roles = {d["role"] for d in result["dates"]}
        self.assertNotIn("first_chapter_publication", roles)
        self.assertIn("first_observed_chapter_publication", roles)
        self.assertIn("last_observed_chapter_publication", roles)
        self.assertEqual(result["chapters"][0]["chapter_id"], "5")

    def test_jjwxc_unlinked_rows_never_invent_ids_or_completion_dates(self):
        body = '''<link rel="canonical" href="https://www.jjwxc.net/onebook.php?novelid=123">
          <span itemprop="articleSection">Book</span><span itemprop="author">Author</span>
          <table><tr itemprop="chapter"><td>1</td><td><span itemprop="headline">全文完</span></td>
          <td title="章节首发时间：2011-01-02 03:04:05">2012-01-01 00:00:00</td></tr></table>'''
        result = jjwxc_detail(Client(body), {"work_id": "123"})
        self.assertEqual(result["chapters"], [])
        self.assertEqual(result["dates"], [])
        self.assertEqual(len(result["meta"]["unverified_chapter_rows"]), 1)
        self.assertEqual(result["meta"]["unverified_chapter_rows"][0]["chapter_id"], "")

    def test_jjwxc_metadata_without_identity_evidence_is_rejected(self):
        body = '<span itemprop="articleSection">Book</span><span itemprop="author">Author</span>'
        with self.assertRaises(FetchError):
            jjwxc_detail(Client(body), {"work_id": "123"})

    def test_jjwxc_without_chapter_links_requires_two_matching_work_widgets(self):
        metadata = '<span itemprop="articleSection">Book</span><span itemprop="author">Author</span>'
        click = '<div id="clickNovelid">123</div>'
        review = '<div id="novelreview_div" data-novelid="123"></div>'
        result = jjwxc_detail(Client(metadata + click + review), {"work_id": "123"})
        self.assertEqual(result["works"][0]["work_id"], "123")
        self.assertEqual(result["chapters"], [])
        self.assertFalse(any(row["role"] == "first_publication" for row in result["dates"]))
        for widgets in (click, review, click + review.replace('123', '999'),
                        click + click + review, click.replace('123', '999') + review):
            with self.subTest(widgets=widgets), self.assertRaises(FetchError):
                jjwxc_detail(Client(metadata + widgets), {"work_id": "123"})
        class RedirectedClient(Client):
            def get(self, url, **kwargs):
                response = super().get(url, **kwargs)
                response.url = "https://www.jjwxc.net/onebook.php?novelid=999"
                return response
        with self.assertRaises(FetchError):
            jjwxc_detail(RedirectedClient(metadata + click + review), {"work_id": "123"})

    def test_jjwxc_author_lock_notice_is_gone_in_utf8_and_gbk(self):
        body = '''<meta name="robots" content="noindex, nofollow">
          <div id="lockpage"><p><span>非常抱歉，相关内容已被作者自行锁定。</span></p>
          <p><a href="//www.jjwxc.net/oneauthor.php?authorid=79527">作者专栏</a></p></div>'''
        for encoding in ("utf-8", "gb18030"):
            with self.subTest(encoding=encoding):
                client = Client(body.encode(encoding))
                with self.assertRaises(FetchError) as caught:
                    jjwxc_detail(client, {"work_id": "100067"})
                self.assertEqual((caught.exception.category, caught.exception.message), ("gone", "jjwxc_author_locked"))
                self.assertEqual(client.urls, ["https://www.jjwxc.net/onebook.php?novelid=100067"])

    def test_jjwxc_admin_lock_notice_requires_exact_template_and_identity(self):
        notice = "非常抱歉，相关内容因出版、修改或者存在色情、有害、原创违规、侵权等原因而被网站管理员锁定或删除。"
        body = '<meta name="robots" content="noindex, nofollow"><div id="lockpage"><p>' + notice + '</p></div>'
        for encoding in ("utf-8", "gb18030"):
            with self.subTest(encoding=encoding), self.assertRaises(FetchError) as caught:
                jjwxc_detail(Client(body.encode(encoding)), {"work_id": "101589"})
            self.assertEqual((caught.exception.category, caught.exception.message),
                             ("gone", "jjwxc_admin_locked_or_deleted"))
        for wrong in (body.replace('id="lockpage"', 'id="other"'),
                      body.replace('noindex, nofollow', 'index, follow'),
                      body.replace(notice, "管理员锁定状态未知，请稍后再试"),
                      body + '<link rel="canonical" href="https://www.jjwxc.net/onebook.php?novelid=999">'):
            with self.subTest(body=wrong), self.assertRaises(FetchError) as caught:
                jjwxc_detail(Client(wrong), {"work_id": "101589"})
            self.assertEqual(caught.exception.category, "invalid")
        class RedirectedClient(Client):
            def get(self, url, **kwargs):
                response = super().get(url, **kwargs)
                response.url = "https://www.jjwxc.net/onebook.php?novelid=999"
                return response
        with self.assertRaises(FetchError) as caught:
            jjwxc_detail(RedirectedClient(body), {"work_id": "101589"})
        self.assertEqual(caught.exception.message, "jjwxc_unavailable_page_identity_mismatch")

    def test_jjwxc_other_missing_metadata_and_lock_messages_are_not_gone(self):
        bodies = (
            '<div>非常抱歉，相关内容已被作者自行锁定。</div>',
            '<meta name="robots" content="noindex, nofollow"><div id="lockpage"><p>请完成安全验证</p></div>',
            '<meta name="robots" content="noindex, nofollow"><div id="lockpage"><p>页面暂时无法显示</p></div>',
            '<meta name="robots" content="noindex, nofollow"><link rel="canonical" href="https://www.jjwxc.net/onebook.php?novelid=999"><div id="lockpage"><p>非常抱歉，相关内容已被作者自行锁定。</p></div>',
        )
        for body in bodies:
            with self.subTest(body=body), self.assertRaises(FetchError) as caught:
                jjwxc_detail(Client(body), {"work_id": "100067"})
            self.assertEqual(caught.exception.category, "invalid")

    def test_jjwxc_lock_notice_for_redirected_work_cannot_mark_requested_work_gone(self):
        body = '<meta name="robots" content="noindex, nofollow"><div id="lockpage"><p>非常抱歉，相关内容已被作者自行锁定。</p></div>'
        class RedirectedClient(Client):
            def get(self, url, **kwargs):
                response = super().get(url, **kwargs)
                response.url = "https://www.jjwxc.net/onebook.php?novelid=999"
                return response
        with self.assertRaises(FetchError) as caught:
            jjwxc_detail(RedirectedClient(body), {"work_id": "100067"})
        self.assertEqual(caught.exception.category, "invalid")
        self.assertEqual(caught.exception.message, "jjwxc_unavailable_page_identity_mismatch")

    def test_jjwxc_lock_notice_quoted_in_real_metadata_is_not_terminal(self):
        body = '''<meta name="robots" content="noindex, nofollow">
          <link rel="canonical" href="https://www.jjwxc.net/onebook.php?novelid=123">
          <span itemprop="articleSection">Book</span><span itemprop="author">Author</span>
          <div id="lockpage"><p>非常抱歉，相关内容已被作者自行锁定。</p></div>'''
        result = jjwxc_detail(Client(body), {"work_id": "123"})
        self.assertEqual(result["works"][0]["work_id"], "123")

    def test_saved_jjwxc_100067_author_lock_notice(self):
        path = Path(__file__).resolve().parents[1] / "data/raw/crawler_diagnostics_20260920/jjwxc_100067.html"
        if not path.exists():
            self.skipTest("Optional saved author-lock diagnostic unavailable")
        client = Client(path.read_bytes())
        with self.assertRaises(FetchError) as caught:
            jjwxc_detail(client, {"work_id": "100067"})
        self.assertEqual((caught.exception.category, caught.exception.message), ("gone", "jjwxc_author_locked"))
        self.assertEqual(len(client.urls), 1)

    def test_jjwxc_vip_reference_is_metadata_and_purchase_action_is_ignored(self):
        body = '''<span itemprop="articleSection">Book</span><span itemprop="author">Author</span>
          <table><tr itemprop="chapter"><td>1</td><td>
          <a href="https://my.jjwxc.net/backend/buynovel.php?t=1&amp;novelid=123&amp;chapterid=1">[VIP]</a>
          <a rel="https://my.jjwxc.net/backend/buynovel.php?t=1&amp;novelid=123&amp;chapterid=1">购买</a>
          <a rel="http://my.jjwxc.net/onebook_vip.php?novelid=123&amp;chapterid=1">VIP chapter title</a></td>
          <td title="章节首发时间：2011-01-02 03:04:05">2012-01-01 00:00:00</td></tr></table>'''
        client = Client(body)
        result = jjwxc_detail(client, {"work_id": "123"})
        self.assertEqual(client.urls, ["https://www.jjwxc.net/onebook.php?novelid=123"])
        self.assertEqual(result["chapters"][0]["chapter_title"], "VIP chapter title")
        self.assertEqual(result["chapters"][0]["chapter_id"], "1")
        self.assertEqual(result["chapters"][0]["is_vip"], 1)
        self.assertIn("/onebook_vip.php?", result["chapters"][0]["chapter_url"])
        self.assertNotIn("/backend/buynovel.php", json.dumps(result))

    def test_jjwxc_vip_reference_still_requires_the_requested_work(self):
        body = '''<span itemprop="articleSection">Book</span><span itemprop="author">Author</span>
          <table><tr itemprop="chapter"><td>1</td><td><a
          href="http://my.jjwxc.net/onebook_vip.php?novelid=999&amp;chapterid=1">VIP chapter</a></td>
          <td title="章节首发时间：2011-01-02 03:04:05">2012-01-01 00:00:00</td></tr></table>'''
        with self.assertRaises(FetchError):
            jjwxc_detail(Client(body), {"work_id": "123"})

    def test_saved_jjwxc_work_page_variants(self):
        directory = Path(__file__).resolve().parents[1] / "data/raw/crawler_diagnostics_20260920"
        if not all((directory / f"jjwxc_{wid}_work.html").exists() for wid in ("1000081", "1000159")):
            self.skipTest("Optional saved public work-page diagnostics unavailable")
        for wid, verified, unresolved, vip in (("1000081", 83, 2, 55), ("1000159", 79, 0, 54)):
            with self.subTest(work_id=wid):
                client = Client((directory / f"jjwxc_{wid}_work.html").read_bytes())
                result = jjwxc_detail(client, {"work_id": wid})
                self.assertEqual(client.urls, [f"https://www.jjwxc.net/onebook.php?novelid={wid}"])
                self.assertEqual(len(result["chapters"]), verified)
                self.assertEqual(len(result["meta"]["unverified_chapter_rows"]), unresolved)
                self.assertEqual(sum(c["is_vip"] for c in result["chapters"]), vip)
                self.assertEqual(len({c["chapter_id"] for c in result["chapters"]}), verified)
                self.assertFalse(any("/backend/buynovel.php" in c["chapter_url"] for c in result["chapters"]))


if __name__ == "__main__":
    unittest.main()
