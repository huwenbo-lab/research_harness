"""Cross-module checks: recoverable budgets and preservation gates."""
import argparse
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import crawl
import crawler_platforms
from crawler_http import BudgetExhausted, FetchError
from crawler_store import Store, canonical
from cloud_state import StateError


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.requests = 0
    def close(self):
        pass


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webnovel-runner-")
        self.root = Path(self.tmp.name)
        self.db = self.root / "state.sqlite"
        self.store = Store(self.db)
        self.store.conn.execute("CREATE TABLE work_master(platform TEXT,platform_work_id TEXT)")
        self.store.conn.execute("INSERT INTO work_master VALUES('qidian','1')")
        self.store.conn.execute("INSERT INTO crawl_meta VALUES('initialized','fixture')")
        self.store.conn.commit()
        self.store.enqueue("qidian", "qidian_catalog", {"page": 1})

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def worker(self, effect):
        with patch.object(crawl, "Client", FakeClient), patch.object(crawl, "run_task", side_effect=effect):
            return crawl.worker(self.db, "qidian", 3, 1200, threading.Event(), ["qidian_catalog"])

    def test_budget_pause_resumes_followup_without_repeating_committed_page(self):
        def first(_client, job):
            if job["params"]["page"] == 2:
                raise BudgetExhausted()
            return {"works": [{"work_id": "1", "title": "one"}], "followups": [
                {"platform": "qidian", "kind": "qidian_catalog", "params": {"page": 2}}]}
        report = self.worker(first)
        self.assertEqual(report["exit_reason"], "budget_exhausted")
        self.assertEqual(report["succeeded"], 1)
        seen = []
        def resume(_client, job):
            seen.append(job["params"]["page"])
            return {}
        self.worker(resume)
        self.assertEqual(seen, [2])
        self.assertEqual(self.store.summary()["counts"]["observations"], 2)

    def test_default_worker_skips_existing_chapter_tasks(self):
        self.store.enqueue("qidian", "qidian_chapters", {"work_id": "1"})
        seen = []
        with patch.object(crawl, "Client", FakeClient), patch.object(crawl, "run_task", side_effect=lambda client, job: seen.append(job["kind"]) or {}):
            crawl.worker(self.db, "qidian", 3, 1200, threading.Event())
        self.assertEqual(seen, ["qidian_catalog"])
        self.assertEqual(self.store.conn.execute("SELECT attempts FROM crawl_jobs WHERE kind='qidian_chapters'").fetchone()[0], 0)

    def test_transient_failure_stays_retryable(self):
        report = self.worker(FetchError("retry", "connection_closed"))
        self.assertEqual(report["errors"], {"retry": 1})
        row = self.store.conn.execute("SELECT status,failure_count FROM crawl_jobs").fetchone()
        self.assertEqual(tuple(row), ("retry", 1))
        self.assertFalse(report["needs_attention"])

    def test_missing_page_is_retained_without_stopping_other_work(self):
        report = self.worker(FetchError("gone", "http_404"))
        self.assertFalse(report["needs_attention"])
        self.assertEqual(report["errors"], {"gone": 1})
        self.assertEqual(self.store.conn.execute("SELECT status FROM crawl_jobs").fetchone()[0], "gone")

    def test_lease_covers_full_batch_budget(self):
        def finish_later(_client, job):
            row = self.store.conn.execute("SELECT lease_until,updated_at FROM crawl_jobs").fetchone()
            self.assertGreaterEqual(row["lease_until"] - row["updated_at"], 1320)
            return {}
        self.assertEqual(self.worker(finish_later)["succeeded"], 1)

    def populated(self):
        job = self.store.claim("qidian")
        self.store.finish(job, {"works": [{"work_id": "1"}],
            "dates": [{"work_id": "1", "role": "platform_publication", "value": "2000-01-01"}],
            "meta": {"partition_key": "cat=1", "page": 1, "page_ids": ["1"]}})

    def test_audit_detects_lost_checkpoint_and_date_identity(self):
        self.populated()
        self.store.export(self.root / "previous")
        previous = self.root / "previous/crawler.sqlite"
        self.assertTrue(crawl.audit_database(self.db, previous)["passed"])
        for table in ("crawl_pages", "crawl_events", "crawl_work_dates"):
            self.store.conn.execute("DELETE FROM " + table)
        self.store.conn.commit()
        result = crawl.audit_database(self.db, previous)
        self.assertFalse(result["passed"])
        self.assertIn("lost_historical_row:crawl_pages", result["errors"])
        self.assertIn("lost_historical_row:crawl_events", result["errors"])
        self.assertIn("lost_record_identity:crawl_work_dates", result["errors"])

    def test_existing_empty_file_is_not_initialized_by_run(self):
        empty = self.root / "empty.sqlite"
        empty.touch()
        with self.assertRaises(StateError):
            crawl.run(argparse.Namespace(db=empty))
        self.assertEqual(empty.stat().st_size, 0)

    def test_failed_init_cleans_its_staging_file(self):
        destination = self.root / "failed.sqlite"
        with patch.object(sys, "argv", ["crawl.py", "init", "--db", str(destination),
                                       "--baseline", str(self.root / "missing.sqlite")]):
            with self.assertRaises(FileNotFoundError):
                crawl.main()
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob("failed.sqlite.init.*")), [])

    def test_split_refuses_a_watch_that_is_between_batches(self):
        destination = self.root / "distributed"
        with crawl.exclusive(Path(str(self.db) + ".watch")):
            with patch.object(sys, "argv", ["crawl.py", "split", "--db", str(self.db),
                                           "--out", str(destination)]):
                with self.assertRaisesRegex(RuntimeError, "another_process"):
                    crawl.main()
        self.assertFalse(destination.exists())

    def test_denied_catalog_api_uses_public_html_without_fetching_api(self):
        urls = []
        client = SimpleNamespace(can_fetch=lambda url: False,
                                 get=lambda url: (urls.append(url) or SimpleNamespace(body=b"public page")))
        with patch("crawler_qidian_html.parse_qidian_category_html", return_value=([
            {"work_id": "1", "title": "one"}], {"coverage": "public_html_partial"})):
            result = crawler_platforms.qidian_catalog(client, {"cat": "10", "page": 1})
        self.assertEqual(urls, ["https://m.qidian.com/category/catid10/"])
        self.assertFalse(result["meta"]["api_requested"])
        self.assertEqual(result["meta"]["coverage"], "public_html_partial")
        self.assertEqual({job["kind"] for job in result["followups"]}, {"qidian_detail", "qidian_dates"})
        job = self.store.claim("qidian")
        self.store.finish(job, result)
        self.assertEqual(self.store.summary()["unresolved_catalog"], 1)

    def test_denied_api_partition_never_becomes_unfiltered_html(self):
        client = SimpleNamespace(can_fetch=lambda url: False)
        with self.assertRaisesRegex(FetchError, "qidian_api_partition_not_permitted"):
            crawler_platforms.qidian_catalog(client, {"cat": "10", "page": 2, "size": "1"})

    def distributed(self, node="cloud"):
        self.populated()
        plan = {"schema_version": 1, "plan_id": "1" * 32,
                "assignments": {"cloud": ["qidian"], "local": ["jjwxc"]},
                "created_at": "2026-09-20T00:00:00Z"}
        self.store.conn.executemany("INSERT INTO crawl_meta VALUES(?,?)", [
            ("distribution_plan", canonical(plan)), ("node_id", node)])

    def args(self, **values):
        args = dict(db=self.db, node=None, platform="auto", kind=None,
                    max_requests=3, max_seconds=1200, start_year=2005, end_year=2005,
                    summary=self.root / "run_summary.json", interval=5, batches=0)
        args.update(values)
        return argparse.Namespace(**args)

    def test_invalid_streak_stops_after_three_and_keeps_remaining_tasks_pending(self):
        for page in range(2, 6):
            self.store.enqueue("qidian", "qidian_catalog", {"page": page})
        report = self.worker(FetchError("invalid", "page_identity_mismatch"))
        self.assertEqual(report["exit_reason"], "repeated_validation_failure")
        self.assertEqual(report["errors"], {"invalid": 3})
        self.assertTrue(report["needs_attention"])
        counts = {row[0]: row[1] for row in self.store.conn.execute("SELECT status,count(*) FROM crawl_jobs GROUP BY status")}
        self.assertEqual(counts, {"invalid": 3, "pending": 2})

    def test_success_resets_consecutive_invalid_count(self):
        for page in range(2, 7):
            self.store.enqueue("qidian", "qidian_catalog", {"page": page})
        report = self.worker([FetchError("invalid", "bad"), FetchError("invalid", "bad"), {},
                              FetchError("invalid", "bad"), FetchError("invalid", "bad"), {}])
        self.assertEqual(report["succeeded"], 2)
        self.assertEqual(report["errors"], {"invalid": 4})
        self.assertEqual(report["exit_reason"], "no_due_tasks")

    def test_expired_lease_after_success_is_recoverable_without_failed_ack(self):
        def woke_up(_client, job):
            self.store.conn.execute("UPDATE crawl_jobs SET lease_until=0 WHERE job_key=?", (job["job_key"],))
            return {}
        report = self.worker(woke_up)
        self.assertEqual(report["exit_reason"], "lease_expired")
        self.assertEqual(report["succeeded"], 0)
        self.assertEqual(self.store.conn.execute("SELECT status,failure_count FROM crawl_jobs").fetchone()[:], ("leased", 0))
        self.assertEqual(self.worker(lambda *_: {})["succeeded"], 1)

    def test_expired_lease_after_error_does_not_escape_worker_or_fail_with_old_token(self):
        errors = [FetchError("retry", "connection_closed"), BudgetExhausted(),
                  ValueError("invalid_page"), RuntimeError("unexpected")]
        for error in errors:
            with self.subTest(error=type(error).__name__):
                self.store.conn.execute("UPDATE crawl_jobs SET status='pending',token=NULL,lease_until=NULL")
                def woke_up(_client, job):
                    self.store.conn.execute("UPDATE crawl_jobs SET lease_until=0 WHERE job_key=?", (job["job_key"],))
                    raise error
                report = self.worker(woke_up)
                self.assertEqual(report["exit_reason"], "lease_expired")
                self.assertEqual(self.store.conn.execute("SELECT status,failure_count FROM crawl_jobs").fetchone()[:], ("leased", 0))

    def test_wrong_node_wrong_platform_and_coordinator_refuse_before_http_client(self):
        self.distributed()
        for node, platform, expected in (("local", "auto", "collector_node_mismatch"),
                                         ("cloud", "jjwxc", "not_assigned"),
                                         ("cloud", "both", "not_assigned")):
            with self.subTest(node=node, platform=platform), patch.object(crawl, "Client") as client:
                with self.assertRaisesRegex(ValueError, expected):
                    crawl.run(self.args(node=node, platform=platform), manage_signals=False)
                client.assert_not_called()
        self.store.conn.execute("UPDATE crawl_meta SET value='coordinator' WHERE key='node_id'")
        with patch.object(crawl, "Client") as client:
            with self.assertRaisesRegex(ValueError, "coordinator_is_merge_only"):
                crawl.run(self.args(), manage_signals=False)
            client.assert_not_called()

    def test_auto_platform_uses_only_assigned_node_and_rejects_foreign_kind(self):
        self.distributed(node="local")
        self.assertEqual(crawl.execution_platforms(self.store, "auto", "local"), ["jjwxc"])
        with patch.object(crawl, "worker", return_value={"needs_attention": False, "halt_required": False, "exit_reason": "no_due_tasks"}) as worker, redirect_stdout(io.StringIO()):
            self.assertEqual(crawl.run(self.args(node="local"), manage_signals=False), 0)
            self.assertEqual(worker.call_count, 1)
            self.assertEqual(worker.call_args.args[1], "jjwxc")
        with patch.object(crawl, "Client") as client:
            with self.assertRaisesRegex(ValueError, "matching platform"):
                crawl.run(self.args(node="local", kind="qidian_detail"), manage_signals=False)
            client.assert_not_called()

    def watch_summary(self, **changes):
        summary = {"jobs": [], "owned_jobs": [], "platforms": [], "owned_platforms": ["jjwxc"]}
        summary.update(changes)
        return summary

    def test_watch_ctrl_c_during_batch_does_not_start_another_batch(self):
        registered = {}
        def register(sig, handler):
            previous = registered.get(sig, signal.SIG_DFL)
            registered[sig] = handler
            return previous
        args = self.args()
        def one_batch(received, stop, manage_signals):
            self.assertFalse(manage_signals)
            crawl.write_json(received.summary, self.watch_summary())
            registered[signal.SIGINT](signal.SIGINT, None)
            self.assertTrue(stop.is_set())
            return 0
        with patch.object(crawl.signal, "signal", side_effect=register), patch.object(crawl, "run", side_effect=one_batch) as run:
            self.assertEqual(crawl.watch(args), 0)
            self.assertEqual(run.call_count, 1)
        self.assertEqual(json.loads(args.summary.read_text())["watch"], {"status": "stopped", "batches_completed": 1})
        self.assertEqual(registered, {signal.SIGINT: signal.SIG_DFL, signal.SIGTERM: signal.SIG_DFL})

    def test_watch_ctrl_c_during_wait_interrupts_wait_without_restarting(self):
        registered, waits = {}, []
        def register(sig, handler):
            previous = registered.get(sig, signal.SIG_DFL)
            registered[sig] = handler
            return previous
        class Event:
            stopped = False
            def is_set(self):
                return self.stopped
            def set(self):
                self.stopped = True
            def wait(self, delay):
                waits.append(delay)
                registered[signal.SIGINT](signal.SIGINT, None)
                return True
        args = self.args()
        def one_batch(received, **_kwargs):
            crawl.write_json(received.summary, self.watch_summary())
            return 0
        with patch.object(crawl.signal, "signal", side_effect=register), patch.object(crawl.threading, "Event", Event), patch.object(crawl, "run", side_effect=one_batch) as run:
            self.assertEqual(crawl.watch(args), 0)
            self.assertEqual(run.call_count, 1)
        self.assertEqual(waits, [5])
        self.assertEqual(json.loads(args.summary.read_text())["watch"]["status"], "stopped")

    def test_watch_repairs_only_its_nodes_invalid_jobs_and_respects_batch_limit(self):
        foreign = {"platform": "qidian", "status": "invalid", "count": 1}
        owned = {"platform": "jjwxc", "status": "invalid", "count": 1}
        args = self.args(batches=1)
        for owned_jobs, expected_code, expected_status in (([], 0, "batch_limit"), ([owned], 1, "repair_required")):
            with self.subTest(owned_jobs=owned_jobs):
                def one_batch(received, **_kwargs):
                    crawl.write_json(received.summary, self.watch_summary(jobs=[foreign, *owned_jobs], owned_jobs=owned_jobs))
                    return 0
                with patch.object(crawl.signal, "signal", return_value=signal.SIG_DFL), patch.object(crawl, "run", side_effect=one_batch) as run:
                    self.assertEqual(crawl.watch(args), expected_code)
                    self.assertEqual(run.call_count, 1)
                self.assertEqual(json.loads(args.summary.read_text())["watch"]["status"], expected_status)

    def test_watch_continues_past_quarantine_but_stops_for_circuit(self):
        owned = {"platform": "jjwxc", "status": "invalid", "count": 1}
        for halt, expected_batches, expected_code in ((False, 2, 0), (True, 1, 1)):
            with self.subTest(halt=halt):
                args = self.args(batches=2, interval=0)
                def one_batch(received, **_kwargs):
                    crawl.write_json(received.summary, self.watch_summary(
                        owned_jobs=[owned], halt_required=halt, needs_attention=True))
                    return 0
                with patch.object(crawl.signal, "signal", return_value=signal.SIG_DFL), patch.object(crawl, "run", side_effect=one_batch) as run:
                    self.assertEqual(crawl.watch(args), expected_code)
                    self.assertEqual(run.call_count, expected_batches)

    def test_retry_invalid_only_requeues_specified_kind_work_and_assigned_platform(self):
        self.distributed(node="cloud")
        tasks = [("qidian", "qidian_detail", "1", "invalid"),
                 ("qidian", "qidian_detail", "2", "invalid"),
                 ("qidian", "qidian_chapters", "1", "invalid"),
                 ("qidian", "qidian_detail", "3", "blocked"),
                 ("qidian", "qidian_detail", "4", "gone"),
                 ("jjwxc", "jjwxc_detail", "1", "invalid"),
                 ("jjwxc", "qidian_detail", "1", "invalid")]
        keys = []
        for platform, kind, wid, status in tasks:
            key = self.store.enqueue(platform, kind, {"work_id": wid})
            self.store.conn.execute("UPDATE crawl_jobs SET status=?,failure_count=2,error_category=? WHERE job_key=?", (status, status, key))
            keys.append(key)
        self.store.block_platform("qidian", "real access control", 86400)
        before = {key: tuple(self.store.conn.execute("SELECT * FROM crawl_jobs WHERE job_key=?", (key,)).fetchone()) for key in keys}
        cooldown = dict(self.store.platform_status("qidian"))
        args = self.args(node="cloud", kind="qidian_detail", work_id="1", reason="parser corrected offline")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(crawl.retry_invalid(args), 0)
        self.assertEqual(tuple(self.store.conn.execute("SELECT status,failure_count FROM crawl_jobs WHERE job_key=?", (keys[0],)).fetchone()), ("pending", 0))
        for key in keys[1:]:
            self.assertEqual(tuple(self.store.conn.execute("SELECT * FROM crawl_jobs WHERE job_key=?", (key,)).fetchone()), before[key])
        self.assertEqual(dict(self.store.platform_status("qidian")), cooldown)

    def rejected_output(self, argv, protected, operation):
        before = {path: path.read_bytes() for path in protected}
        with patch.object(sys, "argv", ["crawl.py", *argv]), patch(operation) as work:
            with self.assertRaisesRegex(ValueError, "output_would_overwrite_"):
                crawl.main()
            work.assert_not_called()
        for path, content in before.items():
            self.assertEqual(path.read_bytes(), content)

    def test_cli_summary_cannot_replace_db_or_db_through_output_alias(self):
        alias = self.root / "looks-like-summary.json"
        alias.symlink_to(self.db)
        hardlink = self.root / "hardlinked-summary.json"
        hardlink.hardlink_to(self.db)
        for output in (self.db, alias, hardlink):
            with self.subTest(output=output):
                self.rejected_output(["run", "--db", str(self.db), "--summary", str(output)], [self.db], "crawl.run")

    def test_cli_merge_rejects_any_source_or_temporary_output_collision_before_merge(self):
        first = self.root / "first.sqlite"
        second = self.root / "summary.json.tmp"
        first.write_bytes(self.db.read_bytes())
        second.write_bytes(self.db.read_bytes())
        for output in (first, second, self.root / "summary.json"):
            with self.subTest(output=output):
                self.rejected_output(["merge", "--db", str(self.db), "--source", str(first), "--source", str(second),
                                      "--summary", str(output)], [self.db, first, second], "crawler_sync.merge_state")

    def test_cli_audit_rejects_previous_input_as_output_or_temporary_file(self):
        previous = self.root / "audit.json.tmp"
        previous.write_bytes(self.db.read_bytes())
        for output in (previous, self.root / "audit.json"):
            with self.subTest(output=output):
                self.rejected_output(["audit", "--db", str(self.db), "--previous", str(previous), "--out", str(output)],
                                     [self.db, previous], "crawl.audit_database")

    def test_cli_watch_rejects_other_sqlite_database_even_without_sqlite_extension(self):
        other = self.root / "another-node.data"
        other.write_bytes(self.db.read_bytes())
        temporary = self.root / "foreign-output.json.tmp"
        temporary.symlink_to(other)
        for output in (other, self.root / "foreign-output.json"):
            with self.subTest(output=output):
                self.rejected_output(["watch", "--db", str(self.db), "--summary", str(output)],
                                     [self.db, other], "crawl.watch")

    def test_cli_export_text_outputs_cannot_overwrite_input_database(self):
        for name in ("works_current.csv", "dates_current.csv", "summary.json"):
            with self.subTest(name=name):
                directory = self.root / ("output-" + name)
                directory.mkdir()
                disguised_db = directory / name
                disguised_db.write_bytes(self.db.read_bytes())
                self.rejected_output(["export", "--db", str(disguised_db), "--out", str(directory)],
                                     [disguised_db], "crawl.Store.export")
                self.assertFalse((directory / "crawler.sqlite").exists())

    def test_cli_export_rejects_csv_alias_to_another_node_database(self):
        directory = self.root / "export"
        directory.mkdir()
        another = self.root / "local.sqlite"
        another.write_bytes(self.db.read_bytes())
        (directory / "works_current.csv").symlink_to(another)
        self.rejected_output(["export", "--db", str(self.db), "--out", str(directory)],
                             [self.db, another], "crawl.Store.export")
        self.assertFalse((directory / "crawler.sqlite").exists())

    def test_cli_export_keeps_existing_safe_same_database_behavior(self):
        self.populated()
        directory = self.root / "export-same-db"
        directory.mkdir()
        database = directory / "crawler.sqlite"
        database.write_bytes(self.db.read_bytes())
        before = database.read_bytes()
        with patch.object(sys, "argv", ["crawl.py", "export", "--db", str(database), "--out", str(directory)]), redirect_stdout(io.StringIO()):
            self.assertEqual(crawl.main(), 0)
        self.assertEqual(database.read_bytes(), before)
        self.assertTrue((directory / "works_current.csv").is_file())
        self.assertTrue((directory / "dates_current.csv").is_file())
        self.assertTrue((directory / "summary.json").is_file())

    def test_cli_resolves_db_before_constructing_watch_and_split_locks(self):
        alias = self.root / "db-alias.sqlite"
        alias.symlink_to(self.db)
        before = self.db.read_bytes()
        out = self.root / "split-alias"
        with crawl.exclusive(Path(str(self.db.resolve()) + ".watch")):
            with patch.object(sys, "argv", ["crawl.py", "split", "--db", str(alias), "--out", str(out)]):
                with self.assertRaisesRegex(RuntimeError, "another_process"):
                    crawl.main()
        self.assertFalse(out.exists())
        self.assertFalse(Path(str(alias) + ".watch.lock").exists())
        with patch.object(sys, "argv", ["crawl.py", "watch", "--db", str(alias)]), patch.object(crawl, "watch", return_value=0) as watch:
            self.assertEqual(crawl.main(), 0)
            self.assertEqual(watch.call_args.args[0].db, self.db.resolve())
            self.assertEqual(watch.call_args.args[0].summary, self.db.resolve().parent / (self.db.stem + "_watch_summary.json"))
        self.assertEqual(self.db.read_bytes(), before)

    def test_json_writer_rechecks_database_headers_after_command_validation(self):
        for path in (self.root / "late.sqlite", self.root / "late.json.tmp"):
            path.write_bytes(self.db.read_bytes())
        before = self.db.read_bytes()
        for output in (self.root / "late.sqlite", self.root / "late.json"):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, "overwrite_sqlite"):
                crawl.write_json(output, {"would": "destroy sqlite"})
        self.assertEqual((self.root / "late.sqlite").read_bytes(), before)
        self.assertEqual((self.root / "late.json.tmp").read_bytes(), before)

    def test_explicit_repair_reclaims_before_later_unprocessed_tasks(self):
        self.distributed(node="cloud")
        repaired = self.store.enqueue("qidian", "qidian_detail", {"work_id": "1"})
        waiting = self.store.enqueue("qidian", "qidian_detail", {"work_id": "2"})
        self.store.conn.execute("UPDATE crawl_jobs SET created_at=100,status='invalid',due_at=500,failure_count=2 WHERE job_key=?", (repaired,))
        self.store.conn.execute("UPDATE crawl_jobs SET created_at=200,due_at=0 WHERE job_key=?", (waiting,))
        args = self.args(node="cloud", kind="qidian_detail", work_id="1", reason="parser fix verified")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(crawl.retry_invalid(args), 0)
        row = self.store.conn.execute("SELECT due_at,created_at,updated_at FROM crawl_jobs WHERE job_key=?", (repaired,)).fetchone()
        self.assertEqual(tuple(row[:2]), (0, 100))
        self.assertGreater(row["updated_at"], 500)
        self.assertEqual(self.store.claim("qidian", "qidian_detail")["job_key"], repaired)


if __name__ == "__main__":
    unittest.main()
