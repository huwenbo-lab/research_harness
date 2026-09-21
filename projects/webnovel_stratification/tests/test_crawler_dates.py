import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from crawler_dates import publication_window


def chapter(number, title, pub="2020-01-01 00:00:00", update="2025-01-01 00:00:00"):
    return {"chapter_id": str(number), "chapter_number_raw": str(number),
            "chapter_title": title, "chapter_url": "https://example.test/" + str(number),
            "publication_date": pub, "update_date": update}


class WindowTests(unittest.TestCase):
    def test_main_end_is_separate_from_later_extra(self):
        rows = [chapter(1, "序章"), chapter(2, "正文完结", "2021-01-01"),
                chapter(3, "番外：多年以后", "2022-01-01")]
        window, dates = publication_window("1", rows, "已完成")
        self.assertEqual(window["main_text_end_candidate"]["chapter_id"], "2")
        self.assertEqual(window["last_visible_chapter"]["chapter_id"], "3")
        self.assertEqual(window["boundary_status"], "candidate_requires_review")
        values = {row["role"]: row["value"] for row in dates}
        self.assertEqual(values["main_text_end_publication_candidate"], "2021-01-01")
        self.assertEqual(values["last_observed_chapter_publication"], "2022-01-01")

    def test_updates_never_become_publication_dates(self):
        window, dates = publication_window("1", [chapter(1, "正文完", None)])
        self.assertTrue(dates)
        self.assertTrue(all("update" in row["role"] for row in dates))
        self.assertIsNone(window["main_text_end_candidate"]["publication_date"])

    def test_missing_first_chapter_is_not_first_publication(self):
        window, dates = publication_window("1", [chapter(5, "第五章")])
        self.assertNotIn("first_chapter_publication", {row["role"] for row in dates})
        self.assertEqual(window["directory_coverage"], "not_independently_verified")

    def test_ongoing_work_last_visible_is_not_end(self):
        window, dates = publication_window("1", [chapter(1, "开端"), chapter(2, "继续")], "连载")
        self.assertIsNone(window["main_text_end_candidate"])
        self.assertFalse(any(row["role"].startswith("main_text_end") for row in dates))

    def test_trailing_extra_boundary_is_only_candidate(self):
        window, _ = publication_window("1", [chapter(1, "最后一幕"), chapter(2, "番外一")])
        self.assertEqual(window["end_basis"], "before_trailing_auxiliary_titles")
        self.assertEqual(window["boundary_status"], "candidate_requires_review")

    def test_announcements_and_ending_commentary_cannot_be_main_text(self):
        rows = [chapter(1, "前言"), chapter(2, "开篇"), chapter(3, "正文完结"),
                chapter(4, "完结感言"), chapter(5, "番外：正文完结")]
        window, _ = publication_window("1", rows)
        self.assertEqual(window["main_text_start_candidate"]["chapter_id"], "2")
        self.assertEqual(window["main_text_end_candidate"]["chapter_id"], "3")

    def test_multiple_ending_markers_require_review_without_selecting_one(self):
        window, _ = publication_window("1", [chapter(1, "正文完"), chapter(2, "正文完结")])
        self.assertIsNone(window["main_text_end_candidate"])
        self.assertEqual(window["end_basis"], "ambiguous_ending_titles")

    def test_completed_status_does_not_verify_last_chapter_as_main_end(self):
        window, _ = publication_window("1", [chapter(1, "最后可见章")], "已完成")
        self.assertEqual(window["end_basis"], "completed_status_last_non_auxiliary")
        self.assertEqual(window["boundary_status"], "candidate_requires_review")

    def test_empty_directory_and_bounded_output(self):
        window, dates = publication_window("1", [])
        self.assertEqual(dates, [])
        self.assertIsNone(window["first_visible_chapter"])
        window, dates = publication_window("1", [chapter(i, "第" + str(i) + "章") for i in range(1, 2001)])
        self.assertLess(len(json.dumps(window)), 3000)
        self.assertLessEqual(len(dates), 9)
        self.assertEqual(window["chapter_count_observed"], 2000)

    def test_volume_auxiliary_marker_is_respected(self):
        rows = [chapter(1, "正文完"), {**chapter(2, "婚后"), "volume": "番外卷"}]
        window, _ = publication_window("1", rows)
        self.assertEqual(window["auxiliary_title_count"], 1)
        self.assertEqual(window["main_text_end_candidate"]["chapter_id"], "1")


if __name__ == "__main__":
    unittest.main()
