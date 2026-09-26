"""Offline recovery boundaries using the same restore/export/audit/publish steps."""
from contextlib import closing
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from cloud_state import POINTER_ASSET, POINTER_TAG, StateError, publish, restore, write_json
import cloud_cycle
from cloud_cycle import BOOTSTRAP_TAG, run_cycle
from crawl import audit_database
from crawler_store import Store
from crawler_sync import split_state


REPO = "research-owner/research-repo"
NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


class MemoryReleases:
    """Store actual snapshot bytes so a restart cannot accidentally use local state."""
    def __init__(self, database):
        self.pointer = {"schema_version": 1, "source_repo": REPO,
                        "tag": "webnovel-crawler-202609", "asset": "crawler-100-1.sqlite.gz",
                        "run_id": "100", "attempt": 1}
        self.assets = {
            (POINTER_TAG, POINTER_ASSET): json.dumps(self.pointer).encode(),
            (self.pointer["tag"], self.pointer["asset"]): gzip.compress(database.read_bytes()),
        }
        self.cancel_pointer = None
        self.fail_asset = None
        self.downloads = []

    def download(self, tag, asset, directory):
        self.downloads.append((tag, asset))
        try:
            body = self.assets[(tag, asset)]
        except KeyError:
            raise StateError("Remote asset unavailable") from None
        path = directory / asset
        path.write_bytes(body)
        return path

    def ensure_monthly_release(self, tag, target):
        pass

    def ensure_pointer_release(self, target):
        pass

    def inventory(self):
        result = {}
        for tag, asset in self.assets:
            if tag != BOOTSTRAP_TAG:
                result.setdefault(tag, set()).add(asset)
        return result

    def upload(self, tag, path, *, replace=False):
        key = (tag, path.name)
        if path.name == self.fail_asset:
            raise StateError("simulated asset upload failure")
        if key in self.assets and not replace:
            raise StateError("Refusing to replace immutable asset")
        if tag == POINTER_TAG and self.cancel_pointer:
            if self.cancel_pointer == "after_delete":
                self.assets.pop(key, None)
            raise KeyboardInterrupt("simulated runner cancellation")
        self.assets[key] = path.read_bytes()


class CloudCycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="webnovel-cloud-cycle-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        baseline = self.root / "baseline.sqlite"
        with closing(sqlite3.connect(baseline)) as conn, conn:
            conn.executescript("""
                CREATE TABLE work_master (platform TEXT, platform_work_id TEXT, title TEXT);
                INSERT INTO work_master VALUES ('qidian', '1', 'preserved baseline');
            """)
        source = self.root / "source.sqlite"
        store = Store(source)
        try:
            store.bootstrap(baseline)
            store.enqueue("qidian", "qidian_catalog", {"page": 1})
        finally:
            store.close()
        self.source = source
        split_state(source, self.root / "distributed")
        self.cloud = self.root / "distributed" / "cloud.sqlite"
        self.remote = MemoryReleases(self.cloud)
        self.original_pointer = self.remote.assets[(POINTER_TAG, POINTER_ASSET)]
        self.db = self.root / "run" / "crawler.sqlite"
        self.receipt = self.root / "run" / "restored.json"
        restore(self.remote, REPO, self.db, self.receipt)
        self.previous = self.root / "previous.sqlite"
        self.previous.write_bytes(self.db.read_bytes())

    def finish_page(self):
        store = Store(self.db)
        try:
            job = store.claim("qidian")
            self.assertEqual(job["params"]["page"], 1)
            store.finish(job, {
                "works": [{"work_id": "2", "title": "newly observed"}],
                "followups": [{"platform": "qidian", "kind": "qidian_catalog", "params": {"page": 2}}],
                "meta": {"partition_key": "test", "page": 1, "page_ids": ["2"]},
            })
        finally:
            store.close()

    def publish_batch(self):
        out = self.root / "export"
        store = Store(self.db)
        try:
            store.export(out)
        finally:
            store.close()
        audit = self.root / "audit.json"
        result = audit_database(out / "crawler.sqlite", self.previous)
        self.assertTrue(result["passed"], result["errors"])
        write_json(audit, result)
        return publish(self.remote, REPO, out / "crawler.sqlite", out / "summary.json", audit,
                       self.receipt, "200", 1, "main", now=NOW)

    def restart_from_remote(self):
        recovered = self.root / "restart" / "crawler.sqlite"
        restore(self.remote, REPO, recovered, self.root / "restart" / "restored.json")
        store = Store(recovered)
        try:
            job = store.claim("qidian")
            count = store.summary()["counts"]["works"]
            return job["params"]["page"], count
        finally:
            store.close()

    def test_cancellation_before_publish_replays_only_unpublished_progress(self):
        self.finish_page()
        self.db.unlink()  # ephemeral runner disk disappears before export
        self.assertEqual(self.remote.assets[(POINTER_TAG, POINTER_ASSET)], self.original_pointer)
        self.assertEqual(self.restart_from_remote(), (1, 1))

    def test_cancellation_after_snapshot_upload_preserves_prior_pointer(self):
        self.finish_page()
        self.remote.cancel_pointer = "before_replace"
        with self.assertRaises(KeyboardInterrupt):
            self.publish_batch()
        self.assertIn(("webnovel-crawler-202609", "crawler-200-1.sqlite.gz"), self.remote.assets)
        self.assertEqual(self.remote.assets[(POINTER_TAG, POINTER_ASSET)], self.original_pointer)
        self.assertEqual(self.restart_from_remote(), (1, 1))

    def test_cancellation_inside_pointer_replacement_fails_closed(self):
        self.finish_page()
        self.remote.cancel_pointer = "after_delete"
        with self.assertRaises(KeyboardInterrupt):
            self.publish_batch()
        recovered = self.root / "restart" / "crawler.sqlite"
        with self.assertRaisesRegex(StateError, "Remote asset unavailable"):
            restore(self.remote, REPO, recovered, self.root / "restart" / "restored.json")
        self.assertFalse(recovered.exists())
        self.assertIn(("webnovel-crawler-202609", "crawler-100-1.sqlite.gz"), self.remote.assets)
        self.assertIn(("webnovel-crawler-202609", "crawler-200-1.sqlite.gz"), self.remote.assets)

    def test_published_batch_resumes_followup_after_runner_loss(self):
        self.finish_page()
        pointer = self.publish_batch()
        self.assertEqual(pointer["run_id"], "200")
        self.db.unlink()
        self.assertEqual(self.restart_from_remote(), (2, 2))

    def cycle_executor(self, *, fail_preflight=False, cancel_batch=None,
                       corrupt_batch=None, attention_batch=None, business_errors=False):
        self.commands = []
        self.executed_batches = 0
        self.previous_work_counts = []

        def execute(argv):
            operation = argv[2]
            values = dict(zip(argv[3::2], argv[4::2]))
            self.commands.append((operation, values))
            database = Path(values["--db"])
            if operation == "audit":
                self.assertEqual(values["--node"], "cloud")
                if "--previous" not in values and fail_preflight:
                    write_json(Path(values["--out"]), {"passed": False})
                    return 1
                previous = Path(values["--previous"]) if "--previous" in values else None
                if previous:
                    with closing(sqlite3.connect(previous)) as conn:
                        self.previous_work_counts.append(conn.execute("SELECT count(*) FROM crawl_works").fetchone()[0])
                report = audit_database(database, previous, expected_node="cloud")
                write_json(Path(values["--out"]), report)
                return 0 if report["passed"] else 1
            if operation == "export":
                store = Store(database)
                try:
                    store.export(Path(values["--out"]))
                finally:
                    store.close()
                return 0
            self.assertEqual(operation, "run")
            self.assertEqual(values["--node"], "cloud")
            self.assertEqual(values["--max-requests"], "50")
            self.assertEqual(values["--max-seconds"], "300")
            self.executed_batches += 1
            if self.executed_batches == cancel_batch:
                raise KeyboardInterrupt("simulated cancellation in a later batch")
            store = Store(database)
            try:
                job = store.claim("qidian")
                page = job["params"]["page"]
                store.finish(job, {
                    "works": [{"work_id": str(page + 1), "title": f"page {page}"}],
                    "followups": [{"platform": "qidian", "kind": "qidian_catalog", "params": {"page": page + 1}}],
                    "meta": {"partition_key": "cycle-test", "page": page, "page_ids": [str(page + 1)]},
                })
                if self.executed_batches == corrupt_batch:
                    store.conn.execute("DELETE FROM crawl_events")
            finally:
                store.close()
            attention = self.executed_batches == attention_batch
            write_json(Path(values["--summary"]), {
                "needs_attention": attention,
                "workers": [{"exit_reason": "no_due_tasks" if business_errors else "budget_exhausted",
                             "errors": {"retry": 1, "gone": 1} if business_errors else {}}],
            })
            return 1 if attention else 0
        return execute

    def cycle(self, executor, **kwargs):
        return run_cycle(self.remote, REPO, self.root / "cycle" / "crawler.sqlite",
                         self.root / "cycle-output", "200", 1, "main", run_command=executor,
                         **kwargs)

    def stage_bootstrap(self):
        self.remote.assets = {
            (BOOTSTRAP_TAG, "cloud.sqlite.gz"): gzip.compress(self.cloud.read_bytes()),
            (BOOTSTRAP_TAG, "previous.sqlite.gz"): gzip.compress(self.source.read_bytes()),
        }
        self.remote.downloads.clear()
        return {"bootstrap_source_asset": "cloud.sqlite.gz",
                "bootstrap_previous_asset": "previous.sqlite.gz"}

    def replace_remote_snapshot(self, database):
        self.remote.assets[(self.remote.pointer["tag"], self.remote.pointer["asset"])] = gzip.compress(database.read_bytes())

    def quarantine_remote_works(self, count):
        store = Store(self.cloud)
        try:
            for work_id in range(10, 10 + count):
                store.enqueue("qidian", "qidian_detail", {"work_id": str(work_id)})
                store.fail(store.claim("qidian", kind="qidian_detail"), "invalid", "qidian_work_metadata_missing")
        finally:
            store.close()
        self.replace_remote_snapshot(self.cloud)

    def reported_health_executor(self, report, *, batch=1, return_code=0):
        execute = self.cycle_executor()

        def override(argv):
            code = execute(argv)
            if argv[2] == "run" and self.executed_batches == batch:
                summary = Path(argv[argv.index("--summary") + 1])
                value = json.loads(summary.read_text())
                value.update(report)
                write_json(summary, value)
                return return_code
            return code
        return override

    def test_explicit_bootstrap_audits_distinct_predecessor_then_runs_three_batches(self):
        inputs = self.stage_bootstrap()
        result = self.cycle(self.cycle_executor(), **inputs)
        self.assertEqual(result["bootstrap_pointer"]["asset"], "crawler-200-1.sqlite.gz")
        self.assertNotIn("batch", result["bootstrap_pointer"])
        self.assertEqual(self.executed_batches, 3)
        self.assertEqual(self.previous_work_counts, [1, 1, 2, 3])
        self.assertEqual(self.remote.downloads[:2], [(BOOTSTRAP_TAG, "cloud.sqlite.gz"),
                                                   (BOOTSTRAP_TAG, "previous.sqlite.gz")])
        self.assertEqual(self.restart_from_remote(), (4, 4))
        summary = json.loads((self.root / "cycle-output/bootstrap/summary.json").read_text())
        self.assertEqual(summary["bootstrap_source"], {"source_repo": REPO, "tag": BOOTSTRAP_TAG,
                                                     "source_asset": "cloud.sqlite.gz",
                                                     "previous_asset": "previous.sqlite.gz"})

    def test_bootstrap_requires_both_safe_distinct_asset_names_before_remote_io(self):
        self.stage_bootstrap()
        bad_pairs = [("cloud.sqlite.gz", None), (None, "previous.sqlite.gz"),
                     ("cloud.sqlite.gz", "cloud.sqlite.gz")]
        for name in ("../cloud.sqlite.gz", "https://other.invalid/cloud.sqlite.gz",
                     "cloud*.sqlite.gz", "cloud.sqlite.gz\n", "-cloud.sqlite.gz"):
            bad_pairs.extend([(name, "previous.sqlite.gz"), ("cloud.sqlite.gz", name)])
        for source, previous in bad_pairs:
            with self.subTest(source=source, previous=previous), self.assertRaises(StateError):
                self.cycle(self.cycle_executor(), bootstrap_source_asset=source,
                           bootstrap_previous_asset=previous)
        self.assertEqual(self.remote.downloads, [])
        self.assertEqual(len(self.remote.assets), 2)

    def test_bootstrap_existing_state_or_orphan_snapshot_refuses_before_download(self):
        before = dict(self.remote.assets)
        with self.assertRaisesRegex(StateError, "already exist"):
            self.cycle(self.cycle_executor(), bootstrap_source_asset="cloud.sqlite.gz",
                       bootstrap_previous_asset="previous.sqlite.gz")
        self.remote.assets.pop((POINTER_TAG, POINTER_ASSET))
        self.remote.downloads.clear()
        with self.assertRaisesRegex(StateError, "already exist"):
            self.cycle(self.cycle_executor(), bootstrap_source_asset="cloud.sqlite.gz",
                       bootstrap_previous_asset="previous.sqlite.gz")
        self.assertEqual(self.remote.downloads, [])
        self.assertEqual(len(self.remote.assets), len(before) - 1)

    def test_bootstrap_inventory_failure_does_not_initialize(self):
        inputs = self.stage_bootstrap()
        with patch.object(self.remote, "inventory", side_effect=StateError("API failed")):
            with self.assertRaisesRegex(StateError, "API failed"):
                self.cycle(self.cycle_executor(), **inputs)
        self.assertEqual(self.remote.downloads, [])
        self.assertEqual(len(self.remote.assets), 2)

    def test_bootstrap_missing_predecessor_stops_without_any_publication(self):
        inputs = self.stage_bootstrap()
        del self.remote.assets[(BOOTSTRAP_TAG, "previous.sqlite.gz")]
        with self.assertRaisesRegex(StateError, "Remote asset unavailable"):
            self.cycle(self.cycle_executor(), **inputs)
        self.assertEqual(self.commands, [])
        self.assertEqual(len(self.remote.assets), 1)

    def test_bootstrap_wrong_node_fails_real_audit_before_publication(self):
        inputs = self.stage_bootstrap()
        self.remote.assets[(BOOTSTRAP_TAG, "cloud.sqlite.gz")] = gzip.compress(
            (self.root / "distributed/local.sqlite").read_bytes())
        with self.assertRaisesRegex(StateError, "preservation audit failed"):
            self.cycle(self.cycle_executor(), **inputs)
        self.assertEqual([operation for operation, _ in self.commands], ["audit"])
        self.assertEqual(len(self.remote.assets), 2)

    def test_bootstrap_lost_predecessor_row_fails_before_publication(self):
        inputs = self.stage_bootstrap()
        with closing(sqlite3.connect(self.cloud)) as conn, conn:
            conn.execute("DELETE FROM work_master")
        self.remote.assets[(BOOTSTRAP_TAG, "cloud.sqlite.gz")] = gzip.compress(self.cloud.read_bytes())
        with self.assertRaisesRegex(StateError, "preservation audit failed"):
            self.cycle(self.cycle_executor(), **inputs)
        self.assertEqual(len(self.remote.assets), 2)

    def test_staging_assets_never_implicitly_initialize_normal_cycle(self):
        self.stage_bootstrap()
        with self.assertRaisesRegex(StateError, "Remote asset unavailable"):
            self.cycle(self.cycle_executor())
        self.assertEqual(self.commands, [])
        self.assertEqual(len(self.remote.assets), 2)

    def test_restored_chapter_failures_are_retired_before_cloud_preflight(self):
        store = Store(self.cloud)
        try:
            store.enqueue("qidian", "qidian_chapters", {"work_id": "1"})
            store.conn.execute("UPDATE crawl_jobs SET status='invalid' WHERE kind='qidian_chapters'")
        finally:
            store.close()
        self.replace_remote_snapshot(self.cloud)
        result = self.cycle(self.cycle_executor(), batches=1)
        self.assertFalse(result["needs_attention"])
        self.assertEqual(self.executed_batches, 1)
        with closing(sqlite3.connect(self.root / "cycle/crawler.sqlite")) as conn:
            self.assertEqual(conn.execute("SELECT status FROM crawl_jobs WHERE kind='qidian_chapters'").fetchone()[0], "excluded")
            self.assertEqual(conn.execute("SELECT value FROM crawl_meta WHERE key='collection_scope'").fetchone()[0], "work_date_endpoints")

    def test_owned_invalid_jobs_stop_before_collection_or_publication(self):
        with closing(sqlite3.connect(self.cloud)) as conn, conn:
            conn.execute("UPDATE crawl_jobs SET status='invalid'")
        self.replace_remote_snapshot(self.cloud)
        before = dict(self.remote.assets)
        result = self.cycle(self.cycle_executor())
        self.assertTrue(result["needs_attention"])
        self.assertEqual(result["exit_reason"], "repair_required")
        self.assertEqual(result["invalid_jobs"][0]["platform"], "qidian")
        self.assertEqual(result["completed_batches"], [])
        self.assertEqual([operation for operation, _ in self.commands], ["audit"])
        self.assertEqual(self.remote.assets, before)
        self.assertEqual(json.loads((self.root / "cycle-output/cloud_summary.json").read_text()), result)

    def test_other_nodes_invalid_jobs_do_not_stop_cloud(self):
        # The physical snapshot preserves all queues; ownership alone controls collection.
        store = Store(self.source)
        try:
            store.enqueue("jjwxc", "jjwxc_detail", {"work_id": "7"})
            store.conn.execute("UPDATE crawl_jobs SET status='invalid' WHERE platform='jjwxc'")
        finally:
            store.close()
        split_state(self.source, self.root / "other-distributed")
        self.replace_remote_snapshot(self.root / "other-distributed/cloud.sqlite")
        result = self.cycle(self.cycle_executor())
        self.assertFalse(result["needs_attention"])
        self.assertEqual(self.executed_batches, 3)

    def test_quarantined_work_survives_publish_and_does_not_block_remaining_batches(self):
        self.quarantine_remote_works(1)
        result = self.cycle(self.reported_health_executor(
            {"needs_attention": True, "halt_required": False, "quarantined_jobs": 1}))
        self.assertEqual(self.executed_batches, 3)
        self.assertTrue(result["needs_attention"])
        self.assertFalse(result["halt_required"])
        self.assertEqual(result["quarantined_jobs"], 1)
        with closing(sqlite3.connect(self.root / "cycle/crawler.sqlite")) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM crawl_jobs WHERE status='invalid'").fetchone()[0], 1)
        # The latest durable receipt must retain the warning after a later batch
        # has no newly encountered invalid response.
        pointer = result["completed_batches"][-1]["pointer"]
        saved = json.loads(self.remote.assets[(pointer["tag"], pointer["asset"].replace(".sqlite.gz", ".summary.json"))])
        self.assertTrue(saved["needs_attention"])
        self.assertFalse(saved["halt_required"])
        self.assertEqual(saved["quarantined_jobs"], 1)

    def test_repeated_missing_metadata_halts_restored_node_without_publication(self):
        self.quarantine_remote_works(3)
        before = dict(self.remote.assets)
        result = self.cycle(self.cycle_executor())
        self.assertTrue(result["halt_required"])
        self.assertTrue(result["needs_attention"])
        self.assertTrue(result["validation_circuits"])
        self.assertEqual(result["completed_batches"], [])
        self.assertEqual([operation for operation, _ in self.commands], ["audit"])
        self.assertEqual(self.remote.assets, before)

    def test_soft_warning_does_not_stop_cycle_or_disappear_from_final_receipt(self):
        result = self.cycle(self.reported_health_executor({"needs_attention": True, "halt_required": False}))
        self.assertEqual(self.executed_batches, 3)
        self.assertTrue(result["needs_attention"])
        self.assertFalse(result["halt_required"])
        self.assertTrue(result["completed_batches"][0]["needs_attention"])
        self.assertFalse(result["completed_batches"][-1]["needs_attention"])

    def test_legacy_attention_summary_still_stops_even_with_zero_exit_code(self):
        result = self.cycle(self.reported_health_executor({"needs_attention": True}))
        self.assertEqual(self.executed_batches, 1)
        self.assertTrue(result["halt_required"])
        self.assertTrue(result["needs_attention"])

    def test_explicit_circuit_halt_is_published_before_stopping(self):
        result = self.cycle(self.reported_health_executor({"needs_attention": True, "halt_required": True}))
        self.assertEqual(self.executed_batches, 1)
        self.assertTrue(result["halt_required"])
        self.assertEqual(self.restart_from_remote(), (2, 2))

    def test_fatal_worker_conditions_override_nonhalting_flag(self):
        for number, worker in enumerate((
                {"exit_reason": "budget_exhausted", "errors": {"internal": 1}},
                {"exit_reason": "budget_exhausted", "errors": {"blocked": 1}},
                {"exit_reason": "interrupted", "errors": {}},
                {"exit_reason": "platform_cooldown", "errors": {}},
                {"exit_reason": "repeated_validation_failure", "errors": {}},
                {"exit_reason": "validation_halted", "errors": {}},
                {"exit_reason": "internal_error", "errors": {}})):
            with self.subTest(worker=worker):
                result = run_cycle(self.remote, REPO, self.root / f"fatal-{number}/crawler.sqlite",
                                   self.root / f"fatal-output-{number}", str(201 + number), 1, "main",
                                   run_command=self.reported_health_executor(
                                       {"needs_attention": False, "halt_required": False, "workers": [worker]}))
                self.assertEqual(self.executed_batches, 1)
                self.assertTrue(result["halt_required"])
                self.assertTrue(result["needs_attention"])

    def test_malformed_worker_or_halting_field_stops_safely(self):
        for number, report in enumerate(({"workers": []}, {"workers": [None]},
                                         {"halt_required": "false"})):
            with self.subTest(report=report):
                result = run_cycle(self.remote, REPO, self.root / f"malformed-{number}/crawler.sqlite",
                                   self.root / f"malformed-output-{number}", str(301 + number), 1, "main",
                                   run_command=self.reported_health_executor(report))
                self.assertEqual(self.executed_batches, 1)
                self.assertTrue(result["halt_required"])
                self.assertTrue(result["needs_attention"])

    def test_cli_warns_without_failure_status_but_halts_exit_nonzero(self):
        argv = ["cloud_cycle.py", "--repo", REPO, "--run-id", "200", "--attempt", "1", "--target", "main"]
        for halt, code in ((False, 0), (True, 1)):
            with self.subTest(halt=halt), patch.object(sys, "argv", argv), \
                    patch.object(cloud_cycle, "run_cycle", return_value={"needs_attention": True, "halt_required": halt}), \
                    patch("builtins.print"):
                self.assertEqual(cloud_cycle.main(), code)

    def test_three_batches_preserve_true_run_identity_and_advance_each_previous(self):
        result = self.cycle(self.cycle_executor())
        self.assertEqual(self.executed_batches, 3)
        self.assertEqual(self.previous_work_counts, [1, 2, 3])
        self.assertFalse(result["needs_attention"])
        pointers = [entry["pointer"] for entry in result["completed_batches"]]
        self.assertEqual([pointer["batch"] for pointer in pointers], [1, 2, 3])
        self.assertEqual({(pointer["run_id"], pointer["attempt"]) for pointer in pointers}, {("200", 1)})
        self.assertEqual([pointer["asset"] for pointer in pointers], [f"crawler-200-1-b{i}.sqlite.gz" for i in (1, 2, 3)])
        self.assertEqual(self.restart_from_remote(), (4, 4))

    def test_failed_cloud_node_preflight_never_collects_exports_or_publishes(self):
        with self.assertRaisesRegex(StateError, "cloud-node audit failed"):
            self.cycle(self.cycle_executor(fail_preflight=True))
        self.assertEqual([operation for operation, _ in self.commands], ["audit"])
        self.assertEqual(self.remote.assets[(POINTER_TAG, POINTER_ASSET)], self.original_pointer)
        self.assertEqual(len(self.remote.assets), 2)

    def test_cancel_in_second_batch_restores_published_first_batch(self):
        with self.assertRaises(KeyboardInterrupt):
            self.cycle(self.cycle_executor(cancel_batch=2))
        pointer = json.loads(self.remote.assets[(POINTER_TAG, POINTER_ASSET)])
        self.assertEqual(pointer["batch"], 1)
        self.assertEqual(self.restart_from_remote(), (2, 2))

    def test_second_batch_upload_failure_does_not_start_third_or_lose_first(self):
        self.remote.fail_asset = "crawler-200-1-b2.summary.json"
        with self.assertRaisesRegex(StateError, "upload failure"):
            self.cycle(self.cycle_executor())
        self.assertEqual(self.executed_batches, 2)
        pointer = json.loads(self.remote.assets[(POINTER_TAG, POINTER_ASSET)])
        self.assertEqual(pointer["batch"], 1)
        self.assertEqual(self.restart_from_remote(), (2, 2))

    def test_second_batch_audit_failure_keeps_first_snapshot(self):
        with self.assertRaisesRegex(StateError, "Batch 2 audit failed"):
            self.cycle(self.cycle_executor(corrupt_batch=2))
        self.assertEqual(self.executed_batches, 2)
        summary = json.loads((self.root / "cycle-output/cloud_summary.json").read_text())
        self.assertTrue(summary["needs_attention"])
        self.assertEqual(summary["failed_batch"], 2)
        self.assertEqual(len(summary["completed_batches"]), 1)
        self.assertEqual(self.restart_from_remote(), (2, 2))

    def test_unexpected_run_failure_is_saved_before_stopping_cycle(self):
        result = self.cycle(self.cycle_executor(attention_batch=1))
        self.assertTrue(result["needs_attention"])
        self.assertEqual(len(result["completed_batches"]), 1)
        self.assertEqual(self.executed_batches, 1)
        self.assertEqual(self.restart_from_remote(), (2, 2))

    def test_retry_and_gone_do_not_stop_remaining_batches(self):
        result = self.cycle(self.cycle_executor(business_errors=True))
        self.assertFalse(result["needs_attention"])
        self.assertEqual(self.executed_batches, 3)


if __name__ == "__main__":
    unittest.main()
