"""LaunchAgent/controller behavior with temporary SQLite and mocked processes."""
from contextlib import contextmanager
import json
from pathlib import Path
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
import local_service as service
from crawler_store import Store, canonical


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="webnovel-service-test-")
        self.root = Path(self.tmp.name).resolve()
        self.db = self.root / "local.sqlite"
        self.directory = self.root / "service"
        self.store = Store(self.db)
        self.store.conn.execute("CREATE TABLE work_master(platform TEXT,platform_work_id TEXT)")
        self.store.conn.execute("INSERT INTO work_master VALUES('jjwxc','1')")
        self.store.conn.execute("INSERT INTO crawl_meta VALUES('initialized','fixture')")
        self.store.enqueue("jjwxc", "jjwxc_detail", {"work_id": "1"})
        self.store.finish(self.store.claim("jjwxc"), {"works": [{"work_id": "1", "title": "temporary test fixture"}]})
        plan = {"schema_version": 1, "plan_id": "1" * 32, "created_at": "2026-09-20T00:00:00Z",
                "assignments": {"cloud": ["qidian"], "local": ["jjwxc"]}}
        self.store.conn.executemany("INSERT INTO crawl_meta VALUES(?,?)", [
            ("distribution_plan", canonical(plan)), ("node_id", "local")])
        service.prepare(self.db, self.directory)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def batch(self, errors=None, status="done", exit_reason="budget_exhausted", **health):
        return {"node_id": "local", "owned_platforms": ["jjwxc"],
                "owned_jobs": [{"platform": "jjwxc", "kind": "jjwxc_detail", "status": status, "count": 1}],
                "workers": [{"platform": "jjwxc", "errors": errors or {}, "exit_reason": exit_reason}],
                **health}

    def quarantine(self, work_id):
        self.store.enqueue("jjwxc", "jjwxc_detail", {"work_id": str(work_id)})
        self.store.fail(self.store.claim("jjwxc", kind="jjwxc_detail"), "invalid", "jjwxc_work_metadata_missing")

    @contextmanager
    def process(self, batch=None, code=0, missing=False, malformed=False, callback=None, timeout=False):
        registered = {}
        def register(sig, handler):
            previous = registered.get(sig, signal.SIG_DFL)
            registered[sig] = handler
            return previous
        class Process:
            pid = 12345
            returncode = None
            terminated = False
            killed = False
            signals = []
            calls = 0
            def __init__(self, command, **kwargs):
                self.command = command
                self.kwargs = kwargs
            def poll(self):
                return self.returncode
            def send_signal(self, sig):
                self.signals.append(sig)
            def terminate(self):
                self.terminated = True
            def kill(self):
                self.killed = True
            def wait(self, timeout=None):
                self.calls += 1
                if callback and self.calls == 1:
                    callback(registered)
                if timeout_mode and self.calls < 3:
                    raise subprocess.TimeoutExpired(self.command, timeout)
                if self.calls == 1 and not missing:
                    summary = Path(self.command[self.command.index("--summary") + 1])
                    summary.write_text("{broken" if malformed else json.dumps(batch or self_batch), encoding="utf-8")
                self.returncode = code
                return code
        self_batch, timeout_mode = self.batch(), timeout
        processes = []
        def popen(command, **kwargs):
            process = Process(command, **kwargs)
            processes.append(process)
            return process
        with patch.object(service.signal, "signal", side_effect=register), patch.object(service.subprocess, "Popen", side_effect=popen) as spawn:
            yield processes, spawn

    def test_prepare_writes_reviewable_plist_without_starting_or_touching_database(self):
        before = self.db.read_bytes()
        with patch.object(service.subprocess, "run") as run:
            result = service.prepare(self.db, self.directory)
            run.assert_not_called()
        self.assertFalse(result["started"])
        with Path(result["plist"]).open("rb") as stream:
            plist = plistlib.load(stream)
        self.assertTrue(plist["RunAtLoad"])
        self.assertFalse(plist["KeepAlive"])
        self.assertEqual(plist["StartInterval"], 2100)
        self.assertEqual(plist["Label"], service.LABEL)
        self.assertEqual(plist["ProgramArguments"][2:], ["tick", "--service-dir", str(self.directory)])
        self.assertTrue(Path(plist["ProgramArguments"][0]).is_absolute())
        self.assertEqual(self.db.read_bytes(), before)

    def test_prepare_and_tick_reject_other_node_before_subprocess(self):
        for node in ("cloud", "coordinator"):
            with self.subTest(node=node):
                self.store.conn.execute("UPDATE crawl_meta SET value=? WHERE key='node_id'", (node,))
                with self.assertRaisesRegex(service.ServiceError, "requires_local"):
                    service.prepare(self.db, self.root / node)
        with patch.object(service.subprocess, "Popen") as popen:
            result = service.tick(self.directory)
            self.assertEqual(result["state"], "paused")
            popen.assert_not_called()

    def test_tick_uses_only_finite_local_command_and_preserves_db(self):
        before = self.db.read_bytes()
        with self.process() as (processes, spawn):
            result = service.tick(self.directory)
        self.assertEqual(result["state"], "ready")
        command = processes[0].command
        for flag, value in (("--node", "local"), ("--platform", "auto"), ("--max-requests", "50"), ("--max-seconds", "300")):
            self.assertEqual(command[command.index(flag) + 1], value)
        self.assertEqual(spawn.call_count, 1)
        self.assertEqual(self.db.read_bytes(), before)
        self.assertFalse((self.directory / "pause.json").exists())

    def test_pause_marker_prevents_validation_and_subprocess_on_later_tick(self):
        service.pause(self.directory, "operator_stop")
        with patch.object(service, "validate_local") as validate, patch.object(service.subprocess, "Popen") as popen:
            result = service.tick(self.directory)
            self.assertEqual(result["state"], "paused")
            self.assertEqual(result["pause"]["reason"], "operator_stop")
            validate.assert_not_called()
            popen.assert_not_called()

    def test_existing_invalid_jobs_pause_before_request(self):
        self.store.conn.execute("UPDATE crawl_jobs SET status='invalid'")
        with patch.object(service.subprocess, "Popen") as popen:
            result = service.tick(self.directory)
            popen.assert_not_called()
        self.assertEqual(result["pause"]["reason"], "preflight_failed")
        self.assertIn("invalid_jobs_require_repair", result["pause"]["detail"])

    def test_new_invalid_output_pauses_but_temporary_retry_does_not(self):
        with self.process(batch=self.batch(errors={"retry": 1}, status="retry")):
            self.assertEqual(service.tick(self.directory)["state"], "ready")
        with self.process(batch=self.batch(errors={"invalid": 1}, status="invalid")) as (_processes, spawn):
            result = service.tick(self.directory)
            self.assertEqual(result["pause"]["reason"], "invalid_jobs")
            service.tick(self.directory)
            self.assertEqual(spawn.call_count, 1)

    def test_one_quarantined_work_stays_visible_without_blocking_resume_or_next_tick(self):
        self.quarantine(2)
        service.pause(self.directory, "invalid_jobs")
        result = service.resume(self.directory, kickstart=False)
        self.assertTrue(result["needs_attention"])
        self.assertEqual(result["quarantined_jobs"], 1)
        self.assertFalse(result["halt_required"])
        with self.process(batch=self.batch(errors={"invalid": 1}, status="invalid",
                                          needs_attention=True, halt_required=False, quarantined_jobs=1)) as (_processes, spawn):
            for _ in range(2):
                result = service.tick(self.directory)
                self.assertEqual(result["state"], "ready")
                self.assertTrue(result["needs_attention"])
                self.assertEqual(result["quarantined_jobs"], 1)
            self.assertEqual(spawn.call_count, 2)
        self.assertEqual(self.store.conn.execute("SELECT count(*) FROM crawl_jobs WHERE status='invalid'").fetchone()[0], 1)
        self.assertFalse((self.directory / "pause.json").exists())

    def test_repeated_missing_metadata_halts_preflight_and_refuses_resume(self):
        for work_id in (2, 3, 4):
            self.quarantine(work_id)
        with patch.object(service.subprocess, "Popen") as popen:
            result = service.tick(self.directory)
            popen.assert_not_called()
        self.assertEqual(result["pause"]["reason"], "preflight_failed")
        self.assertIn("jjwxc", result["pause"]["detail"])
        with self.assertRaisesRegex(service.ServiceError, "invalid_jobs_require_repair"):
            service.resume(self.directory, kickstart=False)

    def test_explicit_halt_and_internal_error_each_pause(self):
        for number, batch in enumerate((
                self.batch(errors={"invalid": 3}, status="invalid", needs_attention=True, halt_required=True),
                self.batch(errors={"internal": 1}, needs_attention=True, halt_required=False))):
            with self.subTest(batch=batch):
                directory = self.root / f"halt-{number}"
                service.prepare(self.db, directory)
                with self.process(batch=batch):
                    result = service.tick(directory)
                self.assertEqual(result["state"], "paused")
                self.assertEqual(result["pause"]["reason"], "collector_internal_error" if number else "invalid_jobs")

    def test_new_database_circuit_overrides_inaccurate_nonhalting_summary(self):
        def fail_three(_registered):
            for work_id in (2, 3, 4):
                self.quarantine(work_id)
        with self.process(batch=self.batch(halt_required=False), callback=fail_three):
            result = service.tick(self.directory)
        self.assertEqual(result["state"], "paused")
        self.assertEqual(result["pause"]["reason"], "invalid_jobs")

    def test_blocked_batch_enters_cooldown_without_permanent_pause(self):
        def block(_registered):
            self.store.block_platform("jjwxc", "server challenge", 86400)
        batch = self.batch(errors={"blocked": 1}, status="blocked", exit_reason="platform_cooldown",
                           needs_attention=True, halt_required=False)
        with self.process(batch=batch, callback=block):
            result = service.tick(self.directory)
        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["needs_attention"])
        with patch.object(service.subprocess, "Popen") as popen:
            self.assertEqual(service.tick(self.directory)["state"], "cooldown")
            popen.assert_not_called()
        self.assertFalse((self.directory / "pause.json").exists())

    def test_cooldown_defers_without_pausing_or_launching(self):
        self.store.block_platform("jjwxc", "server challenge", 86400)
        with patch.object(service.subprocess, "Popen") as popen:
            result = service.tick(self.directory)
            popen.assert_not_called()
        self.assertEqual(result["state"], "cooldown")
        self.assertGreater(result["blocked_until"], time.time())
        self.assertFalse((self.directory / "pause.json").exists())

    def test_fatal_nonzero_missing_malformed_and_wrong_node_summaries_pause(self):
        cases = [({"code": 1}, "collector_exit_nonzero"), ({"missing": True}, "missing_summary"),
                 ({"malformed": True}, "fatal_wrapper_error"),
                 ({"batch": {**self.batch(), "node_id": "cloud"}}, "invalid_summary"),
                 ({"batch": self.batch(halt_required="false")}, "invalid_summary"),
                 ({"batch": {**self.batch(), "workers": [None]}}, "invalid_summary")]
        for number, (options, reason) in enumerate(cases):
            with self.subTest(reason=reason):
                directory = self.root / ("failure-" + str(number))
                service.prepare(self.db, directory)
                with self.process(**options) as (_processes, spawn):
                    result = service.tick(directory)
                    self.assertEqual(result["state"], "paused")
                    self.assertEqual(result["pause"]["reason"], reason)
                    service.tick(directory)
                    self.assertEqual(spawn.call_count, 1)

    def test_timeout_stops_child_and_prevents_next_batch(self):
        with self.process(timeout=True) as (processes, spawn):
            result = service.tick(self.directory)
            self.assertEqual(result["pause"]["reason"], "collector_timeout")
            self.assertTrue(processes[0].terminated)
            self.assertTrue(processes[0].killed)
            service.tick(self.directory)
            self.assertEqual(spawn.call_count, 1)

    def test_system_signal_forwards_stop_without_persistent_pause_and_next_tick_can_run(self):
        def interrupt(registered):
            registered[signal.SIGTERM](signal.SIGTERM, None)
        with self.process(code=-15, missing=True, callback=interrupt) as (processes, _spawn):
            result = service.tick(self.directory)
            self.assertEqual(result["state"], "interrupted")
            self.assertIn(signal.SIGTERM, processes[0].signals)
        self.assertFalse((self.directory / "pause.json").exists())
        with self.process():
            self.assertEqual(service.tick(self.directory)["state"], "ready")

    def test_operator_stop_keeps_pause_when_running_child_exits(self):
        def operator_stop(registered):
            with patch.object(service, "launchctl", return_value=SimpleNamespace(returncode=0)):
                result = service.stop(self.directory)
                self.assertTrue(result["termination_signal_sent"])
            registered[signal.SIGTERM](signal.SIGTERM, None)
        with self.process(code=-15, missing=True, callback=operator_stop) as (_processes, spawn):
            result = service.tick(self.directory)
            self.assertEqual(result["pause"]["reason"], "operator_stop")
            service.tick(self.directory)
            self.assertEqual(spawn.call_count, 1)

    def test_system_shutdown_timeout_still_resumes_after_login(self):
        def interrupt(registered):
            registered[signal.SIGTERM](signal.SIGTERM, None)
        with self.process(code=-9, missing=True, timeout=True, callback=interrupt) as (processes, _spawn):
            result = service.tick(self.directory)
            self.assertEqual(result["state"], "interrupted")
            self.assertTrue(processes[0].killed)
        self.assertFalse((self.directory / "pause.json").exists())

    def test_resume_requires_integrity_local_identity_and_no_invalid_jobs(self):
        marker = service.pause(self.directory, "invalid_jobs")
        self.store.conn.execute("UPDATE crawl_jobs SET status='invalid'")
        with patch.object(service, "launchctl") as launcher:
            with self.assertRaisesRegex(service.ServiceError, "invalid_jobs_require_repair"):
                service.resume(self.directory)
            launcher.assert_not_called()
        self.assertEqual(service.load_json(self.directory / "pause.json"), marker)
        self.store.conn.execute("UPDATE crawl_jobs SET status='pending'")
        before = self.db.read_bytes()
        with patch.object(service, "launchctl", return_value=SimpleNamespace(returncode=0)) as launcher:
            result = service.resume(self.directory)
            launcher.assert_called_once_with(self.directory, "kickstart")
        self.assertTrue(result["kickstart_requested"])
        self.assertFalse((self.directory / "pause.json").exists())
        self.assertEqual(self.db.read_bytes(), before)

    def test_overlapping_ticks_or_resume_do_not_run(self):
        with service.service_lock(self.directory), patch.object(service.subprocess, "Popen") as popen:
            self.assertEqual(service.tick(self.directory)["state"], "already_running")
            with self.assertRaisesRegex(service.ServiceError, "already_running"):
                service.resume(self.directory)
            popen.assert_not_called()

    def test_status_uses_actual_launchctl_output_not_old_saved_pids(self):
        service.receipt(self.directory, "running", wrapper_pid=999, collector_pid=998)
        with patch.object(service, "launchctl", return_value=SimpleNamespace(returncode=0, stdout=" state = running\n pid = 456\n last exit code = 0\n", stderr="")):
            report = service.status(self.directory)
        self.assertEqual(report["launchd"]["pid"], 456)
        self.assertEqual(report["last_receipt"]["wrapper_pid"], 999)
        with patch.object(service, "launchctl", return_value=SimpleNamespace(returncode=113, stdout="", stderr="Could not find service")):
            report = service.status(self.directory)
        self.assertFalse(report["launchd"]["loaded"])
        self.assertNotIn("pid", report["launchd"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
