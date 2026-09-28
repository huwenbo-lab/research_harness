from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from crawler_dates import publication_window
from date_parser_v04 import parse_jj_detail


URL = "https://www.jjwxc.net/onebook.php?novelid=10418464"


def card(number, *, vip=False, tooltip="", update="", title="相遇"):
    link = (f'rel="http://my.jjwxc.net/onebook_vip.php?novelid=10418464&amp;chapterid={number}"'
            if vip else f'href="http://www.jjwxc.net/onebook.php?novelid=10418464&amp;chapterid={number}"')
    return f'''<a itemprop="chapter{' newestChapter' if vip else ''}" {link}>
      <div class="chapterid">{number}</div>
      <div class="chapterinfo"><span itemprop="headline">{title}{' [VIP]' if vip else ''}</span>
        <span>简介中包含另一个日期：2010-01-01</span></div>
      <div class="chaptermeta"><span title="{tooltip}">
        <span class="chaptermeta-item">更新时间：{update}</span></span>
        <span class="chaptermeta-item" itemprop="wordCount">字数：1084</span></div></a>'''


def parse(cards, extra=""):
    body = f'''<meta charset="utf-8"><span itemprop="articleSection">作品</span>
      <span itemprop="author">作者</span>{extra}
      <div id="chapterlist_div">{cards}</div>'''
    return parse_jj_detail(body.encode(), "10418464", URL)


class ChildrenDirectoryTests(unittest.TestCase):
    def test_free_vip_and_newest_token_keep_distinct_dates(self):
        tip = "章节存稿时间：2025-12-23 23:11:27&#13;&#10;章节首发时间：2025-12-31 22:10:00"
        rows = parse(card(12, vip=True, tooltip=tip, update="2026-05-08 18:42:00")
                     + card(1, tooltip=tip, update="2026-05-06 16:56:16"))["chapters"]
        self.assertEqual([row["chapter_id"] for row in rows], ["1", "12"])
        self.assertEqual(rows[0]["publish_time_as_supplied"], "2025-12-31 22:10:00")
        self.assertEqual(rows[0]["draft_time_as_supplied"], "2025-12-23 23:11:27")
        self.assertEqual(rows[0]["update_time_as_supplied"], "2026-05-06 16:56:16")
        self.assertEqual(rows[0]["word_count_raw"], "1084")
        self.assertEqual(rows[0]["is_vip_as_supplied"], 0)
        self.assertEqual(rows[1]["is_vip_as_supplied"], 1)
        self.assertIn("onebook_vip.php?novelid=10418464&chapterid=12", rows[1]["chapter_url"])
        self.assertEqual(rows[1]["chapter_title"], "相遇 [VIP]")

    def test_missing_dates_remain_null_and_updates_never_become_publication(self):
        rows = parse(card(1, tooltip="章节首发时间：未知，更新时间：2026-05-06 16:56:16",
                          update="2026-05-06 16:56:16") + card(2))["chapters"]
        self.assertEqual(len(rows), 2)
        self.assertIsNone(rows[0]["publish_time_as_supplied"])
        self.assertEqual(rows[0]["update_time_as_supplied"], "2026-05-06 16:56:16")
        for key in ("publish_time_as_supplied", "draft_time_as_supplied", "update_time_as_supplied", "date_raw"):
            self.assertIsNone(rows[1][key])
        _, dates = publication_window("10418464", rows)
        self.assertTrue(dates)
        self.assertTrue(all("update" in row["role"] for row in dates))

    def test_completed_card_status_supplies_only_candidate_boundary(self):
        status = '<div class="novelmeta_item_div">文章进度：<span itemprop="updataStatus"><font>完结</font></span></div>'
        parsed = parse(card(1) + card(12, vip=True), status)
        self.assertEqual(parsed["status"], "完结")
        window, _ = publication_window("10418464", parsed["chapters"], parsed["status"])
        self.assertEqual(window["main_text_end_candidate"]["chapter_id"], "12")
        self.assertEqual(window["end_basis"], "completed_status_last_non_auxiliary")
        self.assertEqual(window["boundary_status"], "candidate_requires_review")

    def test_existing_table_and_list_status_take_priority(self):
        old = '''<li>文章进度：连载</li>
          <div class="novelmeta_item_div">文章进度：<span itemprop="updataStatus">完结</span></div>
          <table><tr itemprop="chapter"><td>2</td><td><a href="/onebook.php?novelid=10418464&amp;chapterid=2">旧表章</a></td>
          <td itemprop="wordCount">843</td><td title="章节首发时间：2020-01-01 00:00:00">2025-01-01 00:00:00</td></tr></table>'''
        parsed = parse(card(1), old)
        self.assertEqual(parsed["status"], "连载")
        self.assertEqual(len(parsed["chapters"]), 1)
        row = parsed["chapters"][0]
        self.assertEqual(row["chapter_id"], "2")
        self.assertEqual(row["chapter_title"], "旧表章")
        self.assertEqual(row["publish_time_as_supplied"], "2020-01-01 00:00:00")
        self.assertEqual(row["update_time_as_supplied"], "2025-01-01 00:00:00")

    def test_chapter_identity_is_not_invented_from_ordinal(self):
        parsed = parse(card(7).replace("novelid=10418464", "novelid=999"))
        row = parsed["chapters"][0]
        self.assertEqual(row["chapter_number_raw"], "7")
        self.assertEqual(row["chapter_id"], "")
        self.assertIsNone(row["chapter_url"])


if __name__ == "__main__":
    unittest.main()
