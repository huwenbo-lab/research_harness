"""Offline split/merge regressions using synthetic research databases only."""
import json
from contextlib import closing
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from crawler_store import Store, canonical
from crawler_sync import ASSIGNMENTS, SyncError, merge_state, split_state


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webnovel-sync-test-")
        self.root = Path(self.tmp.name)
        baseline = self.root / "baseline.sqlite"
        with closing(sqlite3.connect(baseline)) as conn, conn:
            conn.executescript("""
                CREATE TABLE work_master(work_key TEXT PRIMARY KEY,platform TEXT,platform_work_id TEXT,title TEXT);
                INSERT INTO work_master VALUES('qidian:1','qidian','1','original'),('jjwxc:2','jjwxc','2','晋江原始作品');
                CREATE TABLE work_dates(work_key TEXT PRIMARY KEY,catalog_pub_date TEXT);
                INSERT INTO work_dates VALUES('qidian:1','2005-01-01');
                CREATE TABLE chapter_metadata(work_key TEXT,chapter_id TEXT,chapter_title TEXT);
                INSERT INTO chapter_metadata VALUES('qidian:1','1','第一章');
            """)
            for number in range(25):
                conn.execute(f"CREATE TABLE historical_{number}(value TEXT)")
                conn.execute(f"INSERT INTO historical_{number} VALUES(?)", ("重复保留 " + str(number),))
                conn.execute(f"INSERT INTO historical_{number} VALUES(?)", ("重复保留 " + str(number),))
        self.source = self.root / "source.sqlite"
        store = Store(self.source)
        try:
            store.bootstrap(baseline)
            store.enqueue("qidian", "qidian_detail", {"work_id": "1"})
            store.enqueue("jjwxc", "jjwxc_detail", {"work_id": "2"})
        finally:
            store.close()
        self.out = self.root / "distributed"
        self.manifest = split_state(self.source, self.out)
        self.coordinator = self.out / "coordinator.sqlite"
        self.cloud = self.out / "cloud.sqlite"
        self.local = self.out / "local.sqlite"
        self.plan = self.manifest["distribution_plan"]

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def rows(path, query, params=()):
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return conn.execute(query, params).fetchall()
        finally:
            conn.close()

    @staticmethod
    def dump(path):
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            return list(conn.iterdump())
        finally:
            conn.close()

    def observe(self, path, wid="1", title="new", observed="2026-09-21T00:00:00Z", **fields):
        store = Store.open_existing(path)
        try:
            node = store.conn.execute("SELECT value FROM crawl_meta WHERE key='node_id'").fetchone()[0]
            platform = ASSIGNMENTS[node][0]
            kind = platform + "_detail"
            params = {"work_id": wid, "test_refresh": observed}
            store.enqueue(platform, kind, params, priority=0)
            job = store.claim(platform, kind=kind, now=time.time())
            output = {"works": [{"work_id": wid, "title": title, **fields}],
                      "dates": [{"work_id": wid, "role": "last_update", "value": observed}],
                      "chapters": [{"work_id": wid, "chapter_id": "10", "chapter_title": title,
                                    "word_count": fields.get("word_count")}],
                      "followups": [{"platform": platform, "kind": follow, "params": {"work_id": wid}}
                                    for follow in ([kind, "qidian_chapters"] if platform == "qidian" else [kind])],
                      "meta": {"source_url": "https://example.invalid/public-metadata", "observed_at": observed,
                               "collector_node": node, "collection_plan": self.plan["plan_id"]}}
            return store.finish(job, output)
        finally:
            store.close()

    def tamper_meta(self, path, changes):
        with closing(sqlite3.connect(path)) as conn, conn:
            for key, value in changes.items():
                conn.execute("UPDATE crawl_meta SET value=? WHERE key=?", (value, key))

    def tamper_observation(self, path, oid, *, columns=None, meta=None):
        with closing(sqlite3.connect(path)) as conn, conn:
            if meta is not None:
                row = conn.execute("SELECT result_json FROM crawl_observations WHERE observation_id=?", (oid,)).fetchone()
                result = json.loads(row[0])
                result["meta"].update(meta)
                conn.execute("UPDATE crawl_observations SET result_json=? WHERE observation_id=?", (canonical(result), oid))
            for key, value in (columns or {}).items():
                self.assertIn(key, {"platform", "source_kind", "recorded_at", "result_json"})
                conn.execute(f"UPDATE crawl_observations SET {key}=? WHERE observation_id=?", (value, oid))

    def test_split_preserves_source_and_all_tables_and_creates_distinct_roles(self):
        before = self.source.read_bytes()
        out = self.root / "another-split"
        manifest = split_state(self.source, out)
        self.assertEqual(self.source.read_bytes(), before)
        self.assertEqual(json.loads((out / "plan.json").read_text()), manifest)
        for node in ("coordinator", "cloud", "local"):
            path = out / (node + ".sqlite")
            self.assertEqual(self.rows(path, "SELECT value FROM crawl_meta WHERE key='node_id'"), [(node,)])
            self.assertEqual(json.loads(self.rows(path, "SELECT value FROM crawl_meta WHERE key='distribution_plan'")[0][0]), manifest["distribution_plan"])
            for table in ("work_master", "historical_0", "crawl_jobs", "crawl_observations", "crawl_works", "crawl_chapters"):
                self.assertEqual(self.rows(path, "SELECT * FROM " + table), self.rows(self.source, "SELECT * FROM " + table))
        self.assertEqual(set(path.name for path in out.iterdir()), {"coordinator.sqlite", "cloud.sqlite", "local.sqlite", "plan.json"})

    def test_split_refuses_existing_output_or_distributed_input(self):
        before = self.dump(self.coordinator)
        with self.assertRaises(FileExistsError):
            split_state(self.source, self.out)
        with self.assertRaisesRegex(SyncError, "already_distributed"):
            split_state(self.cloud, self.root / "again")
        self.assertFalse((self.root / "again").exists())
        self.assertEqual(self.dump(self.coordinator), before)

    def test_split_refuses_active_lease_without_partial_output(self):
        store = Store.open_existing(self.source)
        try:
            store.claim("qidian", now=time.time(), lease_seconds=3600)
        finally:
            store.close()
        before = self.source.read_bytes()
        out = self.root / "active"
        with self.assertRaisesRegex(SyncError, "active_lease"):
            split_state(self.source, out)
        self.assertFalse(out.exists())
        self.assertEqual(self.source.read_bytes(), before)
        self.assertFalse(list(self.root.glob(".active.split-*")))

    def test_split_failure_leaves_no_partial_directory(self):
        out = self.root / "broken"
        before = self.source.read_bytes()
        with patch("crawler_sync.shutil.copyfile", side_effect=OSError("simulated disk failure")):
            with self.assertRaises(OSError):
                split_state(self.source, out)
        self.assertFalse(out.exists())
        self.assertFalse(list(self.root.glob(".broken.split-*")))
        self.assertEqual(self.source.read_bytes(), before)

    def test_merge_is_idempotent_keeps_observation_identity_and_source_unchanged(self):
        oid = self.observe(self.cloud, author="new author")
        source_before = self.cloud.read_bytes()
        original_observation = self.rows(self.cloud, "SELECT * FROM crawl_observations WHERE observation_id=?", (oid,))
        first = merge_state(self.coordinator, self.cloud)
        second = merge_state(self.coordinator, self.cloud)
        self.assertEqual((first["imported_observations"], second["imported_observations"]), (1, 0))
        self.assertEqual(first["historical_tables_compared"], 28)
        self.assertEqual(self.rows(self.coordinator, "SELECT * FROM crawl_observations WHERE observation_id=?", (oid,)), original_observation)
        self.assertEqual(self.rows(self.coordinator, "SELECT count(*) FROM crawl_date_evidence WHERE observation_id=?", (oid,)), [(1,)])
        self.assertEqual(self.rows(self.coordinator, "SELECT count(*) FROM crawl_merge_log"), [(2,)])
        self.assertEqual(self.cloud.read_bytes(), source_before)

    def test_late_snapshot_does_not_overwrite_new_fields_or_erase_missing_fields(self):
        old = self.root / "old-cloud.sqlite"
        shutil.copyfile(self.cloud, old)
        self.observe(old, title="older title", observed="2026-09-21T00:00:00Z", author="old author", synopsis="retained synopsis", word_count=100)
        self.observe(self.cloud, title="newer title", observed="2026-09-22T00:00:00Z", author="new author", synopsis=None, word_count=200)
        merge_state(self.coordinator, self.cloud)
        merge_state(self.coordinator, old)
        metadata = json.loads(self.rows(self.coordinator, "SELECT metadata_json FROM crawl_works WHERE platform='qidian' AND work_id='1'")[0][0])
        self.assertEqual((metadata["title"], metadata["author"], metadata["synopsis"]), ("newer title", "new author", "retained synopsis"))
        self.assertEqual(self.rows(self.coordinator, "SELECT chapter_title,word_count FROM crawl_chapters WHERE chapter_id='10'"), [("newer title", "200")])
        self.assertEqual(self.rows(self.coordinator, "SELECT value FROM crawl_work_dates WHERE role='last_update'"), [("2026-09-22T00:00:00Z",)])

    def test_same_uuid_different_payload_rejects_and_rolls_back(self):
        oid = self.observe(self.cloud)
        merge_state(self.coordinator, self.cloud)
        before = self.dump(self.coordinator)
        self.tamper_observation(self.cloud, oid, columns={"source_kind": "changed source"})
        with self.assertRaisesRegex(SyncError, "observation_id_payload_mismatch"):
            merge_state(self.coordinator, self.cloud)
        self.assertEqual(self.dump(self.coordinator), before)

    def test_cross_plan_wrong_roles_and_history_changes_are_rejected(self):
        other = self.root / "other.sqlite"
        for mutation, expected in (
            ({"distribution_plan": canonical({**self.plan, "plan_id": "0" * 32})}, "distribution_plan_mismatch"),
            ({"node_id": "coordinator"}, "source_must_be_collector"),
            ({"initialized": "unrelated baseline"}, "initialization_identity_mismatch"),
        ):
            with self.subTest(mutation=mutation):
                shutil.copyfile(self.cloud, other)
                self.tamper_meta(other, mutation)
                with self.assertRaisesRegex(SyncError, expected):
                    merge_state(self.coordinator, other)
        with self.assertRaisesRegex(SyncError, "target_must_be_coordinator"):
            merge_state(self.local, self.cloud)
        shutil.copyfile(self.cloud, other)
        with closing(sqlite3.connect(other)) as conn, conn:
            conn.execute("DELETE FROM historical_0 WHERE rowid=(SELECT min(rowid) FROM historical_0)")
        with self.assertRaisesRegex(SyncError, "historical_rows_mismatch"):
            merge_state(self.coordinator, other)

    def test_illegal_platform_or_missing_collection_tags_reject_unknown_observation(self):
        for changes in ({"platform": "jjwxc"}, {"collector_node": "local"}, {"collection_plan": None}):
            with self.subTest(changes=changes):
                other = self.root / "illegal.sqlite"
                shutil.copyfile(self.cloud, other)
                oid = self.observe(other)
                if "platform" in changes:
                    self.tamper_observation(other, oid, columns=changes)
                else:
                    self.tamper_observation(other, oid, meta=changes)
                before = self.dump(self.coordinator)
                with self.assertRaisesRegex(SyncError, "new_observation_"):
                    merge_state(self.coordinator, other)
                self.assertEqual(self.dump(self.coordinator), before)

    def test_failure_after_valid_observation_rolls_back_entire_merge(self):
        self.observe(self.cloud, wid="900", observed="2026-09-21T00:00:00Z")
        bad = self.observe(self.cloud, wid="901", observed="2026-09-22T00:00:00Z")
        self.tamper_observation(self.cloud, bad, meta={"collector_node": "local"})
        before = self.dump(self.coordinator)
        with self.assertRaisesRegex(SyncError, "node_or_plan_mismatch"):
            merge_state(self.coordinator, self.cloud)
        self.assertEqual(self.dump(self.coordinator), before)
        self.assertEqual(self.rows(self.coordinator, "SELECT count(*) FROM crawl_works WHERE work_id='900'"), [(0,)])
        self.assertEqual(self.rows(self.coordinator, "SELECT count(*) FROM sqlite_master WHERE name='crawl_merge_log'"), [(0,)])

    def test_unknown_observation_requires_uuid_and_valid_store_payload(self):
        for corruption in ("uuid", "work_id"):
            with self.subTest(corruption=corruption):
                other = self.root / "malformed.sqlite"
                shutil.copyfile(self.cloud, other)
                oid = self.observe(other)
                with closing(sqlite3.connect(other)) as conn, conn:
                    if corruption == "uuid":
                        # The fixture also updates evidence so integrity remains
                        # valid and the merge's UUID validation is exercised.
                        conn.execute("UPDATE crawl_date_evidence SET observation_id='not-a-uuid' WHERE observation_id=?", (oid,))
                        conn.execute("UPDATE crawl_observations SET observation_id='not-a-uuid' WHERE observation_id=?", (oid,))
                    else:
                        result = json.loads(conn.execute("SELECT result_json FROM crawl_observations WHERE observation_id=?", (oid,)).fetchone()[0])
                        result["works"][0]["work_id"] = "invalid"
                        conn.execute("UPDATE crawl_observations SET result_json=? WHERE observation_id=?", (canonical(result), oid))
                before = self.dump(self.coordinator)
                with self.assertRaises(ValueError):
                    merge_state(self.coordinator, other)
                self.assertEqual(self.dump(self.coordinator), before)

    def test_source_execution_progress_is_reported_but_never_overwrites_target(self):
        self.observe(self.cloud, wid="900")
        store = Store.open_existing(self.cloud)
        try:
            store.enqueue("qidian", "qidian_detail", {"work_id": "901"})
            store.claim("qidian", now=time.time())
            store.block_platform("qidian", "source cooldown", 86400)
        finally:
            store.close()
        jobs_before = self.rows(self.coordinator, "SELECT * FROM crawl_jobs ORDER BY job_key")
        platforms_before = self.rows(self.coordinator, "SELECT * FROM crawl_platforms")
        report = merge_state(self.coordinator, self.cloud)
        for row in jobs_before:
            self.assertEqual(self.rows(self.coordinator, "SELECT * FROM crawl_jobs WHERE job_key=?", (row[0],)), [row])
        self.assertEqual(self.rows(self.coordinator, "SELECT * FROM crawl_platforms"), platforms_before)
        self.assertTrue(any(row["status"] == "leased" for row in report["source_queue"]))
        self.assertEqual(report["source_platforms"][0]["blocked_reason"], "source cooldown")
        self.assertEqual(self.rows(self.coordinator, "SELECT count(*) FROM crawl_jobs WHERE params_json=?", (canonical({"work_id": "900"}),)), [(2,)])

    def test_two_nodes_merge_their_assigned_platforms(self):
        self.observe(self.cloud, wid="100", title="cloud work")
        self.observe(self.local, wid="200", title="local work")
        merge_state(self.coordinator, self.cloud)
        merge_state(self.coordinator, self.local)
        self.assertEqual(self.rows(self.coordinator, "SELECT platform,work_id,title FROM crawl_works WHERE work_id IN ('100','200') ORDER BY work_id"),
                         [("qidian", "100", "cloud work"), ("jjwxc", "200", "local work")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
