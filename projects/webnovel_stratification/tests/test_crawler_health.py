"""Quarantine incomplete work pages without accepting invalid data."""
from pathlib import Path
from contextlib import redirect_stdout
import io
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import crawl
import local_service
from crawler_health import health, read_health
from crawler_http import FetchError
from crawler_store import Store, canonical


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.requests = 0

    def close(self):
        pass


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "test.sqlite"
        self.store = Store(self.db)
        self.addCleanup(self.store.close)

    def enqueue(self, wid):
        return self.store.enqueue("jjwxc", "jjwxc_detail", {"work_id": wid})

    def run_worker(self, effect, kinds=None):
        with patch.object(crawl, "Client", FakeClient), patch.object(crawl, "run_task", side_effect=effect):
            return crawl.worker(self.db, "jjwxc", 50, 300, threading.Event(), kinds)

    def test_missing_metadata_rechecks_then_quarantines_without_committing(self):
        bad = self.enqueue("1")
        for attempt in range(3):
            self.store.conn.execute("UPDATE crawl_jobs SET due_at=0 WHERE job_key=?", (bad,))
            report = self.run_worker(FetchError("invalid", "jjwxc_work_metadata_missing"))
            row = self.store.conn.execute("SELECT status,failure_count FROM crawl_jobs WHERE job_key=?", (bad,)).fetchone()
            self.assertEqual(tuple(row), ("retry" if attempt < 2 else "invalid", attempt + 1))
            self.assertFalse(report["halt_required"])
        self.assertTrue(report["needs_attention"])
        self.assertEqual(self.store.summary()["counts"]["observations"], 0)
        self.assertEqual(self.store.summary()["counts"]["works"], 0)
        self.assertEqual(read_health(self.db, ["jjwxc"])["quarantined_jobs"], 1)
        self.enqueue("2")
        seen = []
        def good(client, job):
            seen.append(job["params"]["work_id"])
            return {"works": [{"work_id": "2", "title": "valid"}]}
        self.assertEqual(self.run_worker(good)["succeeded"], 1)
        self.assertEqual(seen, ["2"])
        self.assertEqual(self.store.summary()["counts"]["works"], 1)

    def test_transient_incomplete_page_can_recover_without_manual_restart(self):
        key = self.enqueue("1")
        self.run_worker(FetchError("invalid", "jjwxc_work_metadata_missing"))
        self.store.conn.execute("UPDATE crawl_jobs SET due_at=0 WHERE job_key=?", (key,))
        report = self.run_worker(lambda *_: {"works": [{"work_id": "1", "title": "valid"}]})
        self.assertEqual(report["succeeded"], 1)
        self.assertFalse(report["needs_attention"])
        self.assertEqual(self.store.conn.execute("SELECT failure_count FROM crawl_jobs").fetchone()[0], 0)

    def test_network_failures_do_not_consume_metadata_rechecks(self):
        key = self.enqueue("1")
        for _ in range(7):
            self.store.conn.execute("UPDATE crawl_jobs SET due_at=0 WHERE job_key=?", (key,))
            job = self.store.claim("jjwxc")
            self.store.fail(job, "retry", "network_error")
        self.store.conn.execute("UPDATE crawl_jobs SET due_at=0 WHERE job_key=?", (key,))
        self.run_worker(FetchError("invalid", "jjwxc_work_metadata_missing"))
        self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs").fetchone()[0], "retry")

    def test_access_block_keeps_cooldown_without_permanent_validation_halt(self):
        self.enqueue("1")
        report = self.run_worker(FetchError("blocked", "http_429", retry_after=3600))
        self.assertEqual(report["exit_reason"], "platform_cooldown")
        self.assertTrue(report["needs_attention"])
        self.assertFalse(report["halt_required"])
        self.assertTrue(self.store.platform_status("jjwxc")["blocked"])

    def test_three_distinct_bad_works_halt_across_batches_despite_catalog_success(self):
        for index in range(3):
            self.enqueue(str(index + 1))
            self.store.enqueue("jjwxc", "jjwxc_catalog", {"page": index + 1})
            def effect(client, job):
                if job["kind"] == "jjwxc_catalog":
                    return {}
                raise FetchError("invalid", "jjwxc_work_metadata_missing")
            report = self.run_worker(effect)
            self.assertEqual(report["halt_required"], index == 2)
        self.assertEqual(report["exit_reason"], "repeated_validation_failure")
        self.assertEqual(health(self.store.conn, ["jjwxc"])["validation_circuits"], ["jjwxc_detail"])
        self.enqueue("4")
        seen = []
        report = self.run_worker(lambda client, job: seen.append(job) or {})
        self.assertEqual(report["exit_reason"], "validation_halted")
        self.assertEqual(seen, [])
        # Use the actual repair CLI: the circuit can trip while all jobs are
        # still retry, before any has become invalid.
        self.store.conn.execute("CREATE TABLE work_master(platform TEXT,platform_work_id TEXT)")
        self.store.conn.execute("INSERT INTO work_master VALUES('jjwxc','0')")
        self.store.conn.execute("INSERT INTO crawl_meta VALUES('initialized','fixture')")
        self.store.enqueue("jjwxc", "jjwxc_catalog", {"page": 999})
        self.store.finish(self.store.claim("jjwxc", kind="jjwxc_catalog"),
                          {"works": [{"work_id": "0", "title": "preserved"}]})
        plan = {"schema_version": 1, "plan_id": "1" * 32,
                "created_at": "2026-09-20T00:00:00Z",
                "assignments": {"local": ["jjwxc"], "cloud": ["qidian"]}}
        self.store.conn.executemany("INSERT INTO crawl_meta VALUES(?,?)", [
            ("distribution_plan", canonical(plan)), ("node_id", "local")])
        network = self.enqueue("5")
        self.store.conn.execute("UPDATE crawl_jobs SET status='retry',due_at=9999999999,error_message='network_error',error_category='retry' WHERE job_key=?", (network,))
        argv = ["crawl.py", "retry-invalid", "--db", str(self.db), "--node", "local",
                "--kind", "jjwxc_detail", "--work-id", "1", "--reason", "parser repaired"]
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(crawl.main(), 0)
        self.assertIn('"requeued": 1', output.getvalue())
        self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs WHERE job_key=?", (network,)).fetchone()[0], "retry")
        self.assertFalse(health(self.store.conn, ["jjwxc"])["halt_required"])
        directory = Path(self.tmp.name) / "service"
        local_service.prepare(self.db, directory)
        local_service.pause(directory, "invalid_jobs")
        self.assertEqual(local_service.resume(directory, kickstart=False)["state"], "ready")
        self.assertEqual(self.run_worker(lambda *_: {})["succeeded"], 2)

    def test_only_success_of_same_kind_resets_missing_metadata_circuit(self):
        for wid in ("1", "2"):
            self.enqueue(wid)
            self.run_worker(FetchError("invalid", "jjwxc_work_metadata_missing"))
        self.enqueue("3")
        self.run_worker(lambda *_: {})
        self.enqueue("4")
        self.run_worker(FetchError("invalid", "jjwxc_work_metadata_missing"))
        self.assertFalse(health(self.store.conn, ["jjwxc"])["halt_required"])

    def test_unknown_identity_catalog_and_internal_errors_are_never_quarantined(self):
        for kind, message in (("jjwxc_detail", "jjwxc_widget_identity_mismatch"),
                              ("jjwxc_detail", "internal_ValueError"),
                              ("jjwxc_detail", "unknown_parse_error"),
                              ("jjwxc_catalog", "jjwxc_work_metadata_missing")):
            with self.subTest(kind=kind, message=message):
                key = self.store.enqueue("jjwxc", kind, {"test": message})
                self.store.conn.execute("UPDATE crawl_jobs SET status='invalid',error_category='invalid',error_message=? WHERE job_key=?", (message, key))
                report = read_health(self.db, ["jjwxc"])
                self.assertTrue(report["halt_required"])
                self.assertEqual(report["quarantined_jobs"], 0)
                self.assertFalse(read_health(self.db, ["qidian"])["halt_required"])


if __name__ == "__main__":
    unittest.main()
