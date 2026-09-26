"""Offline behavioral checks for lease safety, provenance, and recovery."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from crawler_store import LeaseError, Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webnovel-store-test-")
        self.root = Path(self.tmp.name)
        self.path = self.root / "state.sqlite"
        self.store = Store(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def job(self, label, platform="qidian", kind="qidian_detail", now=100):
        self.store.enqueue(platform, kind, {"work_id": label})
        return self.store.claim(platform, kind, now=now)

    def result(self, observed="2026-09-20T00:00:00Z", **kwargs):
        return {"meta": {"observed_at": observed}, **kwargs}

    def configure(self, store, node):
        plan = {"schema_version": 1, "plan_id": "a" * 32,
                "assignments": {"cloud": ["qidian"], "local": ["jjwxc"]},
                "created_at": "2026-09-20T00:00:00Z"}
        store.conn.executemany("INSERT OR REPLACE INTO crawl_meta VALUES(?,?)", [
            ("distribution_plan", json.dumps(plan)), ("node_id", node)])
        return plan

    def remote_observations(self):
        source = Store(":memory:")
        try:
            self.configure(source, "cloud")
            for index, stamp in enumerate(("2026-09-19T00:00:00Z", "2026-09-20T00:00:00Z")):
                source.enqueue("qidian", "qidian_catalog", {"page": 1, "refresh": index})
                job = source.claim("qidian", "qidian_catalog", now=100 + index * 2)
                result = self.result(stamp,
                    works=[{"work_id": "1", "title": "title " + str(index), "author": "author"}],
                    dates=[{"work_id": "1", "role": "last_update", "value": "2026-09-" + str(19 + index)}],
                    chapters=[{"work_id": "1", "chapter_id": "2", "chapter_title": "chapter " + str(index), "publish_time": "2020-01-01"}],
                    followups=[{"platform": "qidian", "kind": "qidian_detail", "params": {"work_id": "1"}}])
                result["meta"].update(source_url="https://example.test/category/1", partition_key="category=1", page=1, page_ids=["1"], coverage="public_html_partial")
                source.finish(job, result, now=101 + index * 2)
            return [dict(row) for row in source.conn.execute("SELECT * FROM crawl_observations ORDER BY observed_ts")]
        finally:
            source.close()

    def test_work_scope_preserves_history_and_excludes_only_chapter_queue(self):
        chapter = self.job("1", kind="qidian_chapters")
        self.store.finish(chapter, self.result(works=[{"work_id": "1"}],
            chapters=[{"work_id": "1", "chapter_id": "1", "chapter_title": "old"}]), next_due=500, now=101)
        self.store.enqueue("qidian", "qidian_detail", {"work_id": "1"})
        self.store.enqueue("qidian", "qidian_chapters", {"work_id": "2"})
        self.store.conn.execute("UPDATE crawl_jobs SET status='invalid',error_message='old failure' WHERE params_json=? AND kind='qidian_chapters'", ('{"work_id":"2"}',))
        old_chapters = [tuple(r) for r in self.store.conn.execute("SELECT * FROM crawl_chapters")]
        old_obs = [tuple(r) for r in self.store.conn.execute("SELECT * FROM crawl_observations")]
        self.assertEqual(self.store.apply_endpoint_scope(), 2)
        self.assertEqual(self.store.apply_endpoint_scope(), 0)
        self.assertEqual([tuple(r) for r in self.store.conn.execute("SELECT * FROM crawl_chapters")], old_chapters)
        self.assertEqual([tuple(r) for r in self.store.conn.execute("SELECT * FROM crawl_observations")], old_obs)
        self.assertIsNone(self.store.claim("qidian", "qidian_chapters"))
        self.assertIsNotNone(self.store.claim("qidian", "qidian_detail"))
        self.assertEqual(self.store.summary()["collection_scope"], "work_date_endpoints")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_events WHERE event='excluded'").fetchone()[0], 2)

    def test_work_scope_cannot_retire_live_chapter_lease(self):
        self.store.enqueue("qidian", "qidian_chapters", {"work_id": "1"})
        self.store.claim("qidian", "qidian_chapters")
        with self.assertRaisesRegex(ValueError, "chapter_worker_still_running"):
            self.store.apply_endpoint_scope()
        self.assertIsNone(self.store.conn.execute("SELECT value FROM crawl_meta WHERE key='collection_scope'").fetchone())

    def test_distribution_ownership_tags_and_summary(self):
        self.assertIsNone(self.store.distribution())
        before_split = self.job("1")
        plan = self.configure(self.store, "local")
        with self.assertRaisesRegex(ValueError, "not assigned"):
            self.store.finish(before_split, self.result(works=[{"work_id": "1"}]), now=101)
        with self.assertRaisesRegex(ValueError, "not assigned"):
            self.store.claim("qidian", now=102)
        self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs").fetchone()[0], "leased")
        local = self.job("2", platform="jjwxc", kind="jjwxc_detail", now=103)
        output = self.result(works=[{"work_id": "2"}])
        self.store.finish(local, output, now=104)
        saved = json.loads(self.store.conn.execute("SELECT result_json FROM crawl_observations").fetchone()[0])
        self.assertEqual(saved["meta"]["collector_node"], "local")
        self.assertEqual(saved["meta"]["collection_plan"], plan["plan_id"])
        self.assertNotIn("collector_node", output["meta"])
        summary = self.store.summary()
        self.assertEqual((summary["node_id"], summary["owned_platforms"], summary["distribution_plan"]), ("local", ["jjwxc"], plan))
        self.assertEqual(self.store.distribution(), {"plan": plan, "node_id": "local", "owned_platforms": ["jjwxc"]})
        self.assertTrue(all(group["platform"] == "jjwxc" for group in summary["owned_jobs"]))
        self.store.conn.execute("UPDATE crawl_meta SET value='coordinator' WHERE key='node_id'")
        self.assertEqual(self.store.summary()["owned_platforms"], [])
        self.assertEqual(self.store.summary()["owned_jobs"], [])
        with self.assertRaisesRegex(ValueError, "not assigned"):
            self.store.claim("jjwxc", now=105)

    def test_invalid_distribution_and_spoofed_result_provenance_rejected(self):
        self.configure(self.store, "local")
        job = self.job("1", platform="jjwxc", kind="jjwxc_detail")
        output = self.result(works=[{"work_id": "1"}])
        output["meta"].update(collector_node="cloud", collection_plan="a" * 32)
        with self.assertRaisesRegex(ValueError, "provenance mismatch"):
            self.store.finish(job, output, now=101)
        self.assertEqual(self.store.summary()["counts"]["observations"], 0)
        self.store.conn.execute("DELETE FROM crawl_meta WHERE key='node_id'")
        with self.assertRaisesRegex(ValueError, "incomplete distribution"):
            self.store.claim("jjwxc", now=102)
        with self.assertRaisesRegex(ValueError, "incomplete distribution"):
            self.store.distribution()

    def test_distribution_validation_matches_sync_exact_plan_contract(self):
        from crawler_sync import _plan, SyncError
        base = self.configure(self.store, "cloud")
        invalid = [
            {**base, "extra": True},
            {key: value for key, value in base.items() if key != "created_at"},
            {**base, "created_at": "2026-09-20"},
            {**base, "created_at": "2026-09-20T00:00:00"},
            {**base, "created_at": None},
            {**base, "schema_version": True},
            {**base, "plan_id": "A" * 32},
            {**base, "assignments": {"cloud": ["jjwxc"], "local": ["qidian"]}},
            {**base, "assignments": {**base["assignments"], "coordinator": []}},
        ]
        for index, plan in enumerate(invalid):
            with self.subTest(case=index):
                self.store.conn.execute("UPDATE crawl_meta SET value=? WHERE key='distribution_plan'", (json.dumps(plan),))
                with self.assertRaises(ValueError):
                    self.store.distribution()
                with self.assertRaises(SyncError):
                    _plan(self.store.conn)
        valid = {**base, "created_at": "2026-09-20T08:00:00+08:00"}
        self.store.conn.execute("UPDATE crawl_meta SET value=? WHERE key='distribution_plan'", (json.dumps(valid),))
        self.assertEqual(self.store.distribution()["plan"], _plan(self.store.conn))

    def test_invalid_scalar_dates_and_chapter_ids_reject_finish_without_ack(self):
        job = self.job("scalar-validation")
        for section, field in (("dates", "value"), ("chapters", "chapter_id")):
            for value in ({"bad": True}, [], ["bad"], True, False):
                with self.subTest(section=section, value=value):
                    output = self.result(works=[{"work_id": "1", "title": "must roll back"}],
                        dates=[{"work_id": "1", "role": "last_update", "value": "2026-09-20"}],
                        chapters=[{"work_id": "1", "chapter_id": "legacy:chapter", "chapter_title": "chapter"}])
                    output[section][0][field] = value
                    with self.assertRaises(ValueError):
                        self.store.finish(job, output, now=101)
                    self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs").fetchone()[0], "leased")
                    for table in ("crawl_works", "crawl_date_evidence", "crawl_chapters", "crawl_observations"):
                        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM " + table).fetchone()[0], 0)
        self.store.finish(job, self.result(
            dates=[{"work_id": "1", "role": "catalog_publication", "value": 2005}],
            chapters=[{"work_id": "1", "chapter_id": "legacy:chapter"}, {"work_id": "1", "chapter_id": 10}]), now=102)
        self.assertEqual(self.store.conn.execute("SELECT value FROM crawl_work_dates").fetchone()[0], "2005")
        self.assertEqual({row[0] for row in self.store.conn.execute("SELECT chapter_id FROM crawl_chapters")}, {"legacy:chapter", "10"})

    def test_invalid_scalars_in_second_import_roll_back_entire_batch(self):
        older, newer = self.remote_observations()
        self.configure(self.store, "coordinator")
        for section, field in (("dates", "value"), ("chapters", "chapter_id")):
            for value in ({"bad": True}, [], True, False):
                with self.subTest(section=section, value=value):
                    payload = json.loads(newer["result_json"])
                    payload[section][0][field] = value
                    with self.assertRaises(ValueError):
                        with self.store._transaction():
                            self.store.import_observation(older)
                            self.store.import_observation({**newer, "result_json": json.dumps(payload)})
                    self.assertEqual(self.store.summary()["counts"]["observations"], 0)
                    self.assertEqual(self.store.summary()["counts"]["date_evidence"], 0)
                    self.assertEqual(self.store.summary()["counts"]["jobs"], 0)

    def test_cross_platform_followups_reject_finish_and_roll_back_import_batch(self):
        job = self.job("followup-validation")
        forbidden = [
            {"platform": "jjwxc", "kind": "jjwxc_detail", "params": {"work_id": "2"}},
            {"kind": "jjwxc_detail", "params": {"work_id": "2"}},
        ]
        for followup in forbidden:
            with self.subTest(followup=followup):
                with self.assertRaisesRegex(ValueError, "platform mismatch"):
                    self.store.finish(job, self.result(works=[{"work_id": "1"}], followups=[followup]), now=101)
        self.assertEqual(self.store.summary()["counts"]["observations"], 0)
        self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs").fetchone()[0], "leased")
        older, newer = self.remote_observations()
        self.configure(self.store, "coordinator")
        before = self.store.summary()["counts"]
        for followup in forbidden:
            payload = json.loads(newer["result_json"])
            payload["followups"].append(followup)
            with self.assertRaisesRegex(ValueError, "platform mismatch"):
                with self.store._transaction():
                    self.store.import_observation(older)
                    self.store.import_observation({**newer, "result_json": json.dumps(payload)})
            self.assertEqual(self.store.summary()["counts"], before)

    def test_import_preserves_rows_is_idempotent_and_keeps_leases_local(self):
        original = self.remote_observations()[0]
        self.configure(self.store, "coordinator")
        with self.assertRaisesRegex(ValueError, "external transaction"):
            self.store.import_observation(original)
        with self.store._transaction():
            self.assertTrue(self.store.import_observation(original))
            self.assertTrue(self.store.conn.in_transaction)
        stored = dict(self.store.conn.execute("SELECT * FROM crawl_observations").fetchone())
        self.assertEqual(stored, original)
        self.assertEqual(self.store.get_work("qidian", "1")["title"], "title 0")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_pages").fetchone()[0], 1)
        job = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
        self.assertEqual((job["kind"], job["status"], job["token"], job["attempts"]), ("qidian_detail", "pending", None, 0))
        self.assertNotEqual(job["job_key"], original["job_key"])
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_events").fetchone()[0], 0)
        counts = self.store.summary()["counts"]
        with self.store._transaction():
            self.assertFalse(self.store.import_observation(original))
        self.assertEqual(self.store.summary()["counts"], counts)
        changed = {**original, "recorded_at": original["recorded_at"] + 1}
        with self.store._transaction():
            with self.assertRaisesRegex(ValueError, "different content"):
                self.store.import_observation(changed)
        self.assertEqual(dict(self.store.conn.execute("SELECT * FROM crawl_observations").fetchone()), original)

    def test_import_out_of_order_retains_newer_current_and_all_evidence(self):
        older, newer = self.remote_observations()
        self.configure(self.store, "local")
        with self.store._transaction():
            self.store.import_observation(newer)
            self.store.import_observation(older)
        self.assertEqual(self.store.get_work("qidian", "1")["title"], "title 1")
        self.assertEqual(self.store.conn.execute("SELECT value FROM crawl_work_dates").fetchone()[0], "2026-09-20")
        self.assertEqual(self.store.conn.execute("SELECT chapter_title FROM crawl_chapters").fetchone()[0], "chapter 1")
        self.assertEqual(self.store.summary()["counts"]["date_evidence"], 2)
        self.assertEqual(self.store.conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_import_validates_identity_platform_time_and_raw_json(self):
        original = self.remote_observations()[0]
        self.configure(self.store, "coordinator")
        malformed = [
            {**original, "observed_ts": original["observed_ts"] + 1},
            {**original, "recorded_at": "100"},
            {**original, "source_url": "https://different.test"},
            {**original, "platform": "jjwxc"},
            {**original, "kind": "qidian_detail"},
            {**original, "result_json": '{"meta":{},"meta":{}}'},
            {**original, "result_json": '{"meta":{},"value":NaN}'},
            {**original, "time_basis": "unknown"},
        ]
        for section, key, value in (("works", "platform", "jjwxc"), ("followups", "platform", "jjwxc"),
                                    ("meta", "collection_plan", "b" * 32), ("meta", "collector_node", "local"),
                                    ("meta", "observed_at", "2025-01-01T00:00:00Z")):
            payload = json.loads(original["result_json"])
            (payload[section] if section == "meta" else payload[section][0])[key] = value
            malformed.append({**original, "result_json": json.dumps(payload)})
        for index, row in enumerate(malformed):
            with self.subTest(case=index), self.store._transaction():
                with self.assertRaises(ValueError):
                    self.store.import_observation(row)
                self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_observations").fetchone()[0], 0)

    def test_summary_latest_coverage_uses_observation_time_after_import(self):
        source = Store(":memory:")
        try:
            self.configure(source, "cloud")
            source.enqueue("qidian", "qidian_catalog", {"page": 1})
            for index, coverage in enumerate(("public_html_partial", "leaf")):
                job = source.claim("qidian", now=100 + 2 * index)
                result = self.result("2026-09-" + str(19 + index) + "T00:00:00Z")
                result["meta"]["coverage"] = coverage
                source.finish(job, result, next_due=102, now=101 + 2 * index)
                if coverage == "public_html_partial":
                    source.conn.execute("UPDATE crawl_jobs SET status='pending'")
            observations = [dict(row) for row in source.conn.execute("SELECT * FROM crawl_observations ORDER BY observed_ts DESC")]
        finally:
            source.close()
        self.configure(self.store, "coordinator")
        with self.store._transaction():
            for row in observations:
                self.store.import_observation(row)
        self.assertEqual(self.store.summary()["unresolved_catalog"], 0)

    def test_import_savepoint_and_caller_rollback_are_atomic(self):
        original = self.remote_observations()[0]
        self.configure(self.store, "coordinator")
        payload = json.loads(original["result_json"])
        payload["works"].append({"work_id": "invalid"})
        with self.store._transaction():
            self.store.conn.execute("INSERT INTO crawl_meta VALUES('caller_marker','keep')")
            with self.assertRaisesRegex(ValueError, "ASCII digits"):
                self.store.import_observation({**original, "result_json": json.dumps(payload)})
            self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_observations").fetchone()[0], 0)
            self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_works").fetchone()[0], 0)
            self.assertEqual(self.store.conn.execute("SELECT value FROM crawl_meta WHERE key='caller_marker'").fetchone()[0], "keep")
        with self.assertRaisesRegex(RuntimeError, "caller abort"):
            with self.store._transaction():
                self.store.import_observation(original)
                raise RuntimeError("caller abort")
        self.assertEqual(self.store.summary()["counts"]["observations"], 0)
        self.assertEqual(self.store.summary()["counts"]["jobs"], 0)

    def test_open_existing_never_creates_or_changes_schema(self):
        before = [tuple(row) for row in self.store.conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name")]
        other = Store.open_existing(self.path)
        try:
            self.assertEqual(other.summary()["counts"], self.store.summary()["counts"])
            self.assertEqual([tuple(row) for row in other.conn.execute("SELECT name,sql FROM sqlite_master ORDER BY name")], before)
        finally:
            other.close()
        empty = self.root / "not-state.sqlite"
        empty.touch()
        with self.assertRaisesRegex(ValueError, "compatible crawler"):
            Store.open_existing(empty)
        self.assertEqual(empty.read_bytes(), b"")
        missing = self.root / "missing-state.sqlite"
        with self.assertRaises(FileNotFoundError):
            Store.open_existing(missing)
        self.assertFalse(missing.exists())

    def test_read_summary_during_write_and_no_initialization(self):
        self.job("1")
        writer = sqlite3.connect(self.path, isolation_level=None)
        try:
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("UPDATE crawl_jobs SET status='done'")
            summary = Store.read_summary(self.path)
            self.assertEqual(summary["counts"]["jobs"], 1)
            self.assertEqual(summary["jobs"][0]["status"], "leased")
            self.assertFalse(summary["initialized"])
        finally:
            writer.rollback()
            writer.close()

        empty = self.root / "empty.sqlite"
        empty.touch()
        with self.assertRaisesRegex(ValueError, "not a crawler state database"):
            Store.read_summary(empty)
        self.assertEqual(empty.read_bytes(), b"")
        missing = self.root / "missing.sqlite"
        with self.assertRaises(FileNotFoundError):
            Store.read_summary(missing)
        self.assertFalse(missing.exists())

    def test_crashed_worker_lease_recovery_and_old_worker_rejected(self):
        first = self.job("1")
        other = Store(self.path)
        try:
            self.assertIsNone(other.claim("qidian", now=399))
            recovered = other.claim("qidian", now=400)
            self.assertEqual(first["job_key"], recovered["job_key"])
            self.assertNotEqual(first["token"], recovered["token"])
            self.assertEqual(recovered["attempts"], 2)
            with self.assertRaises(LeaseError):
                self.store.finish(first, {}, now=401)
            other.finish(recovered, self.result(works=[{"work_id": "1"}]), now=401)
        finally:
            other.close()
        self.assertEqual(self.store.summary()["counts"]["observations"], 1)

    def test_expired_lease_cannot_commit_before_recovery(self):
        job = self.job("1")
        for operation in (lambda: self.store.finish(job, {}, now=400),
                          lambda: self.store.fail(job, "retry", now=400),
                          lambda: self.store.defer(job, "budget", now=400)):
            with self.assertRaises(LeaseError):
                operation()

    def test_duplicate_finish_rejected_without_duplicate_observations(self):
        job = self.job("1")
        self.store.finish(job, self.result(works=[{"work_id": "1"}]), now=101)
        with self.assertRaises(LeaseError):
            self.store.finish(job, self.result(works=[{"work_id": "1"}]), now=102)
        self.assertEqual(self.store.summary()["counts"]["observations"], 1)
        self.assertIsNone(self.store.claim("qidian", now=103))
        self.store.enqueue("qidian", "qidian_detail", {"work_id": "1"})
        self.assertIsNone(self.store.claim("qidian", now=104))

    def test_result_followups_and_ack_are_one_transaction(self):
        job = self.job("1")
        bad = self.result(works=[{"work_id": "1", "title": "should rollback"}],
                          followups=[{"platform": "qidian", "kind": "qidian_detail", "params": {"work_id": "2"}}, {}])
        with self.assertRaises(KeyError):
            self.store.finish(job, bad, now=101)
        self.assertIsNone(self.store.get_work("qidian", "1"))
        self.assertEqual(self.store.summary()["counts"]["observations"], 0)
        self.assertEqual(self.store.summary()["counts"]["jobs"], 1)
        self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs").fetchone()[0], "leased")
        self.store.finish(job, self.result(works=[{"work_id": "1"}]), now=102)

    def test_out_of_order_values_do_not_revert_newer_observations(self):
        newer = self.job("new")
        self.store.finish(newer, self.result(
            works=[{"work_id": "1", "title": "current", "status": "完本", "genre": "玄幻"}],
            dates=[{"work_id": "1", "role": "platform_reported_publication_date", "value": "2020-01-01", "basis": "official"}],
            chapters=[{"work_id": "1", "chapter_id": "99", "chapter_title": "new", "publish_time": "2020-01-01", "update_time": "2026-09-20", "vip": 0}]), now=101)
        older = self.job("old", now=102)
        self.store.finish(older, self.result("2026-09-01T00:00:00Z",
            works=[{"work_id": "1", "title": "old", "status": "连载", "author": "filled from older evidence"}],
            dates=[{"work_id": "1", "role": "platform_reported_publication_date", "value": "2019-01-01", "basis": "older"}],
            chapters=[{"work_id": "1", "chapter_id": "99", "chapter_title": "old", "publish_time": "2019-01-01", "update_time": "2026-09-01", "vip": 1}]), now=103)
        work = self.store.get_work("qidian", "1")
        self.assertEqual((work["title"], work["status"]), ("current", "完本"))
        self.assertEqual(work["author"], "filled from older evidence")
        self.assertEqual(self.store.conn.execute("SELECT value FROM crawl_work_dates").fetchone()[0], "2020-01-01")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_date_evidence").fetchone()[0], 2)
        chapter = self.store.conn.execute("SELECT chapter_title,publication_date,update_date,is_vip FROM crawl_chapters").fetchone()
        self.assertEqual(tuple(chapter), ("new", "2020-01-01", "2026-09-20", 0))
        originals = [json.loads(r[0]) for r in self.store.conn.execute("SELECT result_json FROM crawl_observations")]
        self.assertEqual(originals[1]["works"][0]["title"], "old")

    def test_date_roles_stay_distinct_and_missing_values_do_not_erase(self):
        job = self.job("a")
        self.store.finish(job, self.result(works=[{"work_id": "1", "title": "keep"}], dates=[
            {"work_id": "1", "role": "first_chapter_publication_date", "value": "2020-01-01"},
            {"work_id": "1", "role": "latest_chapter_update_date", "value": "2026-09-19"}]), now=101)
        job = self.job("b", now=102)
        self.store.finish(job, self.result("2026-09-21T00:00:00Z", works=[{"work_id": "1", "title": ""}]), now=103)
        self.assertEqual(self.store.get_work("qidian", "1")["title"], "keep")
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_work_dates").fetchone()[0], 2)

    def test_observed_catalog_endpoints_are_distinct_from_work_first_and_last(self):
        job = self.job("observed")
        rows = [
            {"work_id": "1", "role": "first_chapter_publication", "value": "2000-01-01"},
            {"work_id": "1", "role": "first_observed_chapter_publication", "value": "2010-01-01"},
            {"work_id": "1", "role": "last_chapter_publication", "value": "2020-01-01"},
            {"work_id": "1", "role": "last_observed_chapter_publication", "value": "2019-01-01"},
        ]
        self.store.finish(job, self.result(dates=rows), now=101)
        current = dict(self.store.conn.execute("SELECT role,value FROM crawl_work_dates"))
        self.assertEqual(current, {r["role"]: r["value"] for r in rows})
        self.assertEqual(self.store.summary()["counts"]["conflicts"], 0)

    def test_equivalent_platform_timestamps_keep_representation_and_evidence(self):
        original = "2013-09-21T13:36:56+08:00"
        local = "2013-09-21 13:36:56"
        job = self.job("date-formats")
        self.store.finish(job, self.result(dates=[
            {"work_id": "1", "role": "last_update", "value": original},
            {"work_id": "1", "role": "last_update", "value": local}]), now=101)
        self.assertEqual(self.store.summary()["counts"]["conflicts"], 0)
        self.assertEqual([r[0] for r in self.store.conn.execute("SELECT value FROM crawl_date_evidence ORDER BY evidence_id")], [original, local])
        newer = self.job("newer-date-format", now=102)
        self.store.finish(newer, self.result("2026-09-21T00:00:00Z", dates=[
            {"work_id": "1", "role": "last_update", "value": "2013-09-21T05:36:56Z"}]), now=103)
        self.assertEqual(self.store.conn.execute("SELECT value FROM crawl_work_dates").fetchone()[0], original)
        self.assertEqual(self.store.summary()["counts"]["date_evidence"], 3)
        self.assertEqual(self.store.summary()["counts"]["conflicts"], 0)

    def test_date_precision_and_genuinely_different_times_remain_conflicts(self):
        pairs = [
            ("2013-09-21T13:36:56+08:00", "2013-09-21 13:36:57"),
            ("2013-09-21T13:36:56+08:00", "2013-09-21T13:36:56Z"),
            ("2013", "2013-01-01"),
            ("2013-09-21", "2013-09-21T00:00:00+08:00"),
            ("2013-09-21T13:36+08:00", "2013-09-21T13:36:00+08:00"),
            ("2013-09-21T13:36:56+08:00", "2013-09-21T13:36:56.000+08:00"),
            ("2013-09-21T13:36:56.1+08:00", "2013-09-21T13:36:56.10+08:00"),
            ("2013-02-30T13:36:56+08:00", "2013-02-30 13:36:56"),
        ]
        for index, (left, right) in enumerate(pairs, 1):
            with self.subTest(left=left, right=right):
                job = self.job("date-conflict-" + str(index), now=100 + index * 2)
                self.store.finish(job, self.result(dates=[
                    {"work_id": str(index), "role": "last_update", "value": left},
                    {"work_id": str(index), "role": "last_update", "value": right}]), now=101 + index * 2)
        self.assertEqual(self.store.summary()["counts"]["conflicts"], len(pairs))
        self.assertEqual(self.store.summary()["counts"]["date_evidence"], 2 * len(pairs))

    def test_equal_timestamp_conflicts_are_retained_and_reported(self):
        first = self.job("first")
        self.store.finish(first, self.result(works=[{"work_id": "1", "title": "kept"}], dates=[{"work_id": "1", "role": "platform_publication", "value": "2000-01-01"}]), now=101)
        second = self.job("second", now=102)
        self.store.finish(second, self.result(works=[{"work_id": "1", "title": "conflicting"}], dates=[{"work_id": "1", "role": "platform_publication", "value": "2001-01-01"}]), now=103)
        self.assertEqual(self.store.get_work("qidian", "1")["title"], "kept")
        self.assertEqual(self.store.summary()["counts"]["conflicts"], 2)
        self.assertEqual(self.store.summary()["counts"]["observations"], 2)

    def test_automatic_sample_class_tracks_genre_but_explicit_class_wins(self):
        first = self.job("a", platform="jjwxc", kind="jjwxc_detail")
        self.store.finish(first, self.result(works=[{"work_id": "1", "genre": "评论"}]), now=101)
        self.assertEqual(self.store.get_work("jjwxc", "1")["sample_class"], "non_novel")
        second = self.job("b", platform="jjwxc", kind="jjwxc_detail", now=102)
        self.store.finish(second, self.result("2026-09-21T00:00:00Z", works=[{"work_id": "1", "genre": "原创-言情-近代现代-爱情"}]), now=103)
        self.assertEqual(self.store.get_work("jjwxc", "1")["sample_class"], "novel_like")
        third = self.job("c", platform="jjwxc", kind="jjwxc_detail", now=104)
        self.store.finish(third, self.result("2026-09-22T00:00:00Z", works=[{"work_id": "1", "sample_class": "manually_reviewed"}]), now=105)
        fourth = self.job("d", platform="jjwxc", kind="jjwxc_detail", now=106)
        self.store.finish(fourth, self.result("2026-09-23T00:00:00Z", works=[{"work_id": "1", "genre": "诗歌"}]), now=107)
        self.assertEqual(self.store.get_work("jjwxc", "1")["sample_class"], "manually_reviewed")

    def test_budget_exhaustion_and_unresolved_catalog_are_not_done(self):
        job = self.job("budget", kind="qidian_catalog")
        self.store.finish(job, {"meta": {"coverage": "budget_exhausted"}}, now=101)
        row = self.store.conn.execute("SELECT status,completed_at,failure_count FROM crawl_jobs").fetchone()
        self.assertEqual(tuple(row), ("pending", None, 0))
        job = self.store.claim("qidian", now=102)
        self.store.finish(job, {"meta": {"coverage": "api_cap_unresolved"}}, now=103)
        row = self.store.conn.execute("SELECT status,completed_at FROM crawl_jobs").fetchone()
        self.assertEqual(tuple(row), ("unresolved", None))
        self.assertEqual(self.store.summary()["unresolved_catalog"], 1)

    def test_unverified_partitions_and_page_limits_stay_unresolved_with_followups(self):
        for number, coverage in enumerate(("page_limit_unresolved", "partitioned_unverified"), 1):
            with self.subTest(coverage=coverage):
                self.store.enqueue("jjwxc", "jjwxc_catalog", {"year": 2000 + number, "filters": {}, "depth": 0, "page": 1})
                job = self.store.claim("jjwxc", "jjwxc_catalog", now=100 + number)
                output = self.result(works=[{"work_id": str(number), "title": "discovered", "genre_raw": "未知"}],
                                     followups=[{"platform": "jjwxc", "kind": "jjwxc_detail", "params": {"work_id": str(number)}}])
                output["meta"].update(coverage=coverage, page=1, partition_key='{"year":' + str(2000 + number) + '}', page_ids=[str(number)])
                self.store.finish(job, output, now=110 + number)
                row = self.store.conn.execute("SELECT status,completed_at FROM crawl_jobs WHERE job_key=?", (job["job_key"],)).fetchone()
                self.assertEqual(tuple(row), ("unresolved", None))
                self.assertIsNone(self.store.claim("jjwxc", "jjwxc_catalog", now=120 + number))
        self.assertEqual(self.store.summary()["unresolved_catalog"], 2)
        self.assertEqual(self.store.summary()["counts"]["works"], 2)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_jobs WHERE kind='jjwxc_detail' AND status='pending'").fetchone()[0], 2)

    def test_invalid_identity_is_rejected_atomically(self):
        with self.assertRaisesRegex(ValueError, "unsupported platform"):
            self.store.enqueue("elsewhere", "detail", {})
        job = self.job("1")
        for wid in ("１２３", "123junk", "", None):
            with self.assertRaisesRegex(ValueError, "ASCII digits"):
                self.store.finish(job, self.result(works=[{"work_id": wid}]), now=101)
        self.assertEqual(self.store.summary()["counts"]["works"], 0)

    def test_chapter_fallback_identity_is_readable_and_not_a_hash(self):
        job = self.job("a")
        self.store.finish(job, self.result(chapters=[{"work_id": "1", "chapter_title": "尾声", "chapter_url": "https://example.test/read/1"}]), now=101)
        key = self.store.conn.execute("SELECT chapter_key FROM crawl_chapters").fetchone()[0]
        self.assertEqual(key, 'title_url:["尾声","https://example.test/read/1"]')

    def test_retry_backoff_is_bounded_and_defer_does_not_count_failure(self):
        job = self.job("1")
        self.store.defer(job, "request budget used", now=101)
        row = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
        self.assertEqual(row["failure_count"], 0)
        self.assertEqual(row["status"], "pending")
        now = 102
        for attempt in range(20):
            job = self.store.claim("qidian", now=now)
            status = self.store.fail(job, "retry", "remote disconnected", now=now + 1)
            row = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
            self.assertEqual(status, "retry")
            self.assertEqual(row["error_category"], "retry")
            self.assertEqual(row["failure_count"], attempt + 1)
            delay = row["due_at"] - (now + 1)
            self.assertLessEqual(delay, self.store.MAX_BACKOFF)
            if attempt < 4:
                self.assertEqual(delay, (30, 60, 120, 240)[attempt])
            if attempt + 1 >= self.store.RETRY_SLOWDOWN_AFTER:
                self.assertGreaterEqual(delay, 3600)
            self.assertIsNone(self.store.claim("qidian", now=row["due_at"] - 1))
            now = row["due_at"]
        self.assertEqual(delay, self.store.MAX_BACKOFF)
        job = self.store.claim("qidian", now=now)
        self.assertIsNotNone(job)
        self.store.finish(job, self.result(works=[{"work_id": "1", "title": "recovered"}]), next_due=now + 1000, now=now + 1)
        row = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
        self.assertEqual((row["status"], row["failure_count"]), ("pending", 0))
        self.assertIsNone(row["error_category"])
        self.assertIsNone(row["error_message"])
        now = row["due_at"]
        job = self.store.claim("qidian", now=now)
        self.store.fail(job, "retry", "network_error", now=now + 1)
        row = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
        self.assertEqual(row["failure_count"], 1)
        self.assertEqual(row["due_at"] - (now + 1), 30)

    def test_retry_handles_large_failure_count_and_honors_longer_server_delay(self):
        job = self.job("1")
        self.store.conn.execute("UPDATE crawl_jobs SET failure_count=1000000")
        self.assertEqual(self.store.fail(job, "retry", "network_error", now=101), "retry")
        row = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
        self.assertEqual(row["failure_count"], 1000001)
        self.assertEqual(row["due_at"] - 101, self.store.MAX_BACKOFF)
        now = row["due_at"]
        job = self.store.claim("qidian", now=now)
        server_delay = self.store.MAX_BACKOFF * 2
        self.assertEqual(self.store.fail(job, "retry", "http_server_error", retry_after=server_delay, now=now + 1), "retry")
        row = self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()
        self.assertEqual(row["due_at"], now + 1 + server_delay)
        self.assertIsNone(self.store.claim("qidian", now=row["due_at"] - 1))
        self.assertIsNotNone(self.store.claim("qidian", now=row["due_at"]))

    def test_legacy_invalid_retry_is_not_silently_migrated_or_claimed(self):
        job = self.job("1")
        self.store.fail(job, "invalid", "network_error", now=101)
        self.store.conn.execute("UPDATE crawl_jobs SET error_category='retry',failure_count=5")
        before = dict(self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone())
        self.store.close()
        self.store = Store(self.path)
        self.assertIsNone(self.store.claim("qidian", now=1000000))
        self.assertEqual(dict(self.store.conn.execute("SELECT * FROM crawl_jobs").fetchone()), before)

    def test_blocked_gone_invalid_categories_and_persistent_cooldown(self):
        job = self.job("block")
        self.assertEqual(self.store.fail(job, "blocked", "challenge", retry_after=60, now=101), "blocked")
        self.assertEqual(self.store.platform_status("qidian", now=102)["blocked_reason"], "challenge")
        self.assertIsNone(self.store.claim("qidian", now=200))
        self.store.enqueue("jjwxc", "jjwxc_detail", {"work_id": "gone"})
        job = self.store.claim("jjwxc", now=200)
        self.assertEqual(self.store.fail(job, "gone", now=201), "gone")
        job = self.job("invalid", platform="jjwxc", kind="jjwxc_detail", now=202)
        self.assertEqual(self.store.fail(job, "invalid", "identity mismatch", now=203), "invalid")
        self.assertIsNone(self.store.claim("jjwxc", now=100000))

    def test_rate_reservation_is_shared_between_connections(self):
        other = Store(self.path)
        try:
            self.assertEqual(self.store.reserve_request("qidian", 3, now=100), 0)
            self.assertEqual(other.reserve_request("qidian", 3, now=100), 3)
            self.store.block_platform("qidian", "slow down", 30, now=100)
            self.assertEqual(other.reserve_request("qidian", 3, now=101), 29)
            self.assertEqual(self.store.platform_status("qidian", now=101)["next_request_at"], 133)
        finally:
            other.close()

    def test_repeated_catalog_page_rolls_back_without_followups(self):
        first = self.job("page1", kind="qidian_catalog")
        self.store.finish(first, {"meta": {"partition_key": "cat=5", "page": 1, "page_ids": ["2", "1"]}}, now=101)
        second = self.job("page2", kind="qidian_catalog", now=102)
        with self.assertRaisesRegex(ValueError, "repeated_catalog_page"):
            self.store.finish(second, {"meta": {"partition_key": "cat=5", "page": 2, "page_ids": ["2", "1"]}, "followups": [{"platform": "qidian", "kind": "qidian_catalog", "params": {"page": 3}}]}, now=103)
        self.assertEqual(self.store.summary()["counts"]["observations"], 1)
        self.assertEqual(self.store.summary()["counts"]["jobs"], 2)
        self.store.defer(second, "validation pending", now=104)
        # Refreshing the same page is valid even when its ID sequence is unchanged.
        self.store.enqueue("qidian", "refresh", {"page": 1})
        refresh = self.store.claim("qidian", "refresh", now=105)
        self.store.finish(refresh, {"meta": {"partition_key": "cat=5", "page": 1, "page_ids": ["2", "1"]}}, now=106)

    def test_enqueue_many_and_readable_canonical_keys(self):
        items = [{"platform": "qidian", "kind": "qidian_detail", "params": {"b": 2, "a": 1}}, {"platform": "qidian", "kind": "qidian_detail", "params": {"a": 1, "b": 2}}]
        self.assertEqual(self.store.enqueue_many(iter(items)), 1)
        job = self.store.claim("qidian", now=100)
        self.assertEqual(job["job_key"], '["qidian","qidian_detail",{"a":1,"b":2}]')
        self.store.finish(job, {"meta": {"coverage": "api_cap_unresolved"}}, now=101)
        self.assertEqual(self.store.summary()["unresolved_catalog"], 1)

    def sources(self):
        baseline, live = self.root / "baseline.sqlite", self.root / "live.sqlite"
        c = sqlite3.connect(baseline)
        c.executescript("""
        CREATE TABLE work_master(work_key TEXT PRIMARY KEY,platform TEXT,platform_work_id TEXT,title TEXT,genre_raw TEXT,status_raw TEXT,platform_declared_pub_year INTEGER);
        CREATE TABLE work_dates(work_key TEXT PRIMARY KEY,catalog_pub_date TEXT,first_chapter_publication_date TEXT,latest_chapter_update_date TEXT,notes TEXT);
        CREATE TABLE chapter_metadata(work_key TEXT,chapter_id TEXT,chapter_title TEXT,publish_time_as_supplied TEXT,update_time_as_supplied TEXT,is_vip_as_supplied TEXT);
        INSERT INTO work_master VALUES('jjwxc:1','jjwxc','1','评论作品','评论','完结',2005),('jjwxc:2','jjwxc','2','unknown',NULL,'连载',2006),('qidian:3','qidian','3','old title','玄幻','连载',2007);
        INSERT INTO work_dates VALUES('jjwxc:1','2005-01-01','2005-01-02','2008-03-04','Do not merge these date roles');
        INSERT INTO chapter_metadata VALUES('jjwxc:1','1','chapter','2005-01-02','2008-03-04','False');
        """)
        for i in range(25):
            c.execute('CREATE TABLE historical_' + str(i) + '(value TEXT)')
            c.execute('INSERT INTO historical_' + str(i) + ' VALUES(?)', ("保留证据 " + str(i),))
        c.commit()
        c.close()
        c = sqlite3.connect(live)
        c.executescript("""
        CREATE TABLE works(platform TEXT,work_id TEXT,title TEXT,genre TEXT,status TEXT,last_seen_at TEXT);
        CREATE TABLE work_dates(platform TEXT,work_id TEXT,platform_reported_publication_date TEXT,publication_date_basis TEXT,date_observed_at TEXT);
        CREATE TABLE chapters(platform TEXT,work_id TEXT,chapter_key TEXT,chapter_title TEXT,publication_date TEXT,update_date TEXT,is_vip INTEGER,observed_at TEXT);
        INSERT INTO works VALUES('qidian','3','live title','玄幻','完本','2099-01-01'),('qidian','4','new','玄幻','连载','2099-01-01');
        INSERT INTO work_dates VALUES('qidian','3','2007-01-01','schema.org Book','2026-09-19');
        INSERT INTO chapters VALUES('qidian','3','chapter-3','chapter','2007-01-01','2008-01-01',1,'2099-01-01');
        """)
        c.commit()
        c.close()
        return baseline, live

    def test_bootstrap_preserves_all_original_tables_ids_roles_and_source_times(self):
        baseline, live = self.sources()
        source = sqlite3.connect(baseline)
        names = [r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        expected = {n: source.execute("SELECT * FROM " + n).fetchall() for n in names}
        before_schema = source.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        source.close()
        self.store.bootstrap(baseline, live)
        self.assertEqual(len(names), 28)
        for name, rows in expected.items():
            self.assertEqual([tuple(r) for r in self.store.conn.execute("SELECT * FROM " + name)], rows)
        source = sqlite3.connect(baseline)
        self.assertEqual(source.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall(), before_schema)
        source.close()
        self.assertEqual({(r["platform"], r["work_id"]) for r in self.store.iter_works()}, {("jjwxc", "1"), ("jjwxc", "2"), ("qidian", "3"), ("qidian", "4")})
        self.assertEqual(self.store.get_work("jjwxc", "1")["sample_class"], "non_novel")
        self.assertEqual(self.store.get_work("qidian", "3")["title"], "live title")
        self.assertIsNone(self.store.get_work("qidian", "3")["last_observed_at"])
        self.assertEqual(self.store.get_work("qidian", "3")["metadata"]["last_seen_at"], "2099-01-01")
        roles = {r[0] for r in self.store.conn.execute("SELECT role FROM crawl_work_dates WHERE platform='jjwxc'")}
        self.assertEqual(roles, {"catalog_publication", "first_chapter_publication", "last_update"})
        job = self.job("3")
        self.store.finish(job, self.result(works=[{"work_id": "3", "title": "actual observation"}]), now=101)
        self.assertEqual(self.store.get_work("qidian", "3")["title"], "actual observation")
        self.assertEqual(self.store.conn.execute("PRAGMA foreign_key_check").fetchall(), [])
        exported = self.store.export(self.root / "export")
        self.assertEqual(json.loads((self.root / "export/summary.json").read_text())["counts"], exported["counts"])
        self.assertTrue((self.root / "export/works_current.csv").is_file())
        snapshot = sqlite3.connect(self.root / "export/crawler.sqlite")
        self.assertEqual(snapshot.execute("SELECT count(*) FROM work_master").fetchone()[0], 3)
        self.assertEqual(snapshot.execute("SELECT count(*) FROM crawl_works").fetchone()[0], 4)
        snapshot.close()
        with self.assertRaisesRegex(ValueError, "already initialized"):
            self.store.bootstrap(baseline, live)

    def test_bootstrap_failure_leaves_state_uninitialized_and_recoverable(self):
        baseline, _ = self.sources()
        invalid = self.root / "invalid.sqlite"
        sqlite3.connect(invalid).close()
        with self.assertRaisesRegex(ValueError, "live works table missing"):
            self.store.bootstrap(baseline, invalid)
        self.assertFalse(self.store.summary()["initialized"])
        self.assertEqual(self.store.summary()["counts"]["works"], 0)
        self.assertFalse(list(self.root.glob("*.tmp")))
        self.store.bootstrap(baseline)
        self.assertTrue(self.store.summary()["initialized"])

    def test_legacy_per_chapter_dates_stay_evidence_without_work_dates_or_conflicts(self):
        baseline, _ = self.sources()
        c = sqlite3.connect(baseline)
        c.execute("CREATE TABLE date_candidate(work_key TEXT,date_role TEXT,date_value TEXT,row_locator TEXT,chapter_id TEXT)")
        legacy = []
        for role in ("chapter_publication", "chapter_publication_tooltip", "chapter_update"):
            for chapter, value in (("1", "2005-01-02"), ("2", "2005-02-03")):
                legacy.append(("jjwxc:1", role, value, "chapter_ordinal:" + chapter, chapter))
        c.executemany("INSERT INTO date_candidate VALUES(?,?,?,?,?)", legacy)
        c.commit()
        c.close()
        self.store.bootstrap(baseline)
        self.assertEqual([tuple(r) for r in self.store.conn.execute("SELECT * FROM date_candidate")], legacy)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_work_dates WHERE role IN ('chapter_publication','chapter_publication_tooltip','chapter_update')").fetchone()[0], 0)
        rows = self.store.conn.execute("SELECT role,value,raw_json FROM crawl_date_evidence WHERE role IN ('chapter_publication','chapter_publication_tooltip','chapter_update')").fetchall()
        self.assertEqual(len(rows), 6)
        self.assertEqual({json.loads(row["raw_json"])["chapter_id"] for row in rows}, {"1", "2"})
        self.assertTrue(all(json.loads(row["raw_json"])["row_locator"].startswith("chapter_ordinal:") for row in rows))
        self.assertEqual(self.store.summary()["counts"]["conflicts"], 0)

    def test_source_database_cannot_be_opened_as_writable_state(self):
        baseline, live = self.sources()
        for source in (baseline, live):
            with self.assertRaisesRegex(ValueError, "separate state path"):
                Store(source)
            c = sqlite3.connect(source)
            self.assertEqual(c.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'crawl_%'").fetchone()[0], 0)
            c.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
