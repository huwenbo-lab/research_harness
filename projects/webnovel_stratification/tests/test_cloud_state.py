"""Offline cloud-state contract tests; no GitHub requests or file hashes."""
from __future__ import annotations

import copy
import gzip
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from cloud_state import (GitHubReleases, POINTER_ASSET, POINTER_TAG, StateError,
                         bootstrap, publish, restore, validate_pointer, write_json)
from crawler_store import Store


REPO = "research-owner/research-repo"
POINTER = {"schema_version": 1, "source_repo": REPO, "tag": "webnovel-crawler-202609",
           "asset": "crawler-100-1.sqlite.gz", "run_id": "100", "attempt": 1}


class FakeReleases:
    def __init__(self, database: Path):
        self.pointer = copy.deepcopy(POINTER)
        self.database = database
        self.downloads = []
        self.uploads = []
        self.releases = []
        self.fail_snapshot = False
        self.fail_asset = None
        self.change_after_upload = False
        self.invalid_database = False
        self.fail_inventory = False
        self.inventory_reads = 0
        self.assets = {POINTER_TAG: {POINTER_ASSET}, POINTER["tag"]: {POINTER["asset"]}}

    def download(self, tag, asset, directory):
        self.downloads.append((tag, asset))
        path = directory / asset
        if tag == POINTER_TAG:
            if self.pointer is None:
                raise StateError("State pointer download failed")
            write_json(path, self.pointer)
        else:
            if self.fail_snapshot:
                raise StateError("Previous snapshot is unavailable")
            body = b"not sqlite" if self.invalid_database else self.database.read_bytes()
            with gzip.open(path, "wb") as stream:
                stream.write(body)
        return path

    def ensure_monthly_release(self, tag, target):
        self.releases.append((tag, target))
        self.assets.setdefault(tag, set())

    def ensure_pointer_release(self, target):
        self.ensure_monthly_release(POINTER_TAG, target)

    def inventory(self):
        self.inventory_reads += 1
        if self.fail_inventory:
            raise StateError("Inventory API unavailable")
        return copy.deepcopy(self.assets)

    def upload(self, tag, path, *, replace=False):
        self.uploads.append((tag, path.name, replace, path.read_bytes()))
        if path.name == self.fail_asset:
            raise StateError("Upload failed")
        if not replace and path.name in self.assets.setdefault(tag, set()):
            raise StateError("Asset already exists")
        self.assets[tag].add(path.name)
        if tag == POINTER_TAG:
            self.pointer = json.loads(path.read_text(encoding="utf-8"))
        elif self.change_after_upload:
            self.pointer = dict(POINTER, run_id="101", asset="crawler-101-1.sqlite.gz")


class CloudStateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.sqlite"
        baseline = self.root / "baseline.sqlite"
        with closing(sqlite3.connect(baseline)) as conn, conn:
            conn.executescript("""
                CREATE TABLE work_master (platform TEXT, platform_work_id TEXT, title TEXT);
                INSERT INTO work_master VALUES ('jjwxc', '1', 'old research evidence');
            """)
        store = Store(self.source)
        try:
            store.bootstrap(baseline)
            store.enqueue("jjwxc", "jjwxc_detail", {"work_id": "1"})
        finally:
            store.close()
        self.store = FakeReleases(self.source)
        self.out = self.root / "state" / "crawler.sqlite"
        self.receipt = self.root / "state" / "restored.json"
        self.summary = self.root / "summary.json"
        self.audit = self.root / "audit.json"

    def prepare_publish(self):
        restore(self.store, REPO, self.out, self.receipt)
        write_json(self.summary, {"needs_attention": True, "exit_reason": "blocked"})
        write_json(self.audit, {"passed": True, "database": str(self.out.resolve()),
                                "previous": str(self.source.resolve()),
                                "checked_at": "2026-09-20T00:00:00+00:00"})

    def publish(self, batch=None):
        return publish(self.store, REPO, self.out, self.summary, self.audit, self.receipt,
                       "200", 2, "main", now=datetime(2026, 9, 20, tzinfo=timezone.utc), batch=batch)

    def prepare_bootstrap(self):
        self.store.pointer = None
        self.store.assets = {}
        write_json(self.summary, {"initialized": True})
        write_json(self.audit, {"passed": True, "database": str(self.source.resolve()),
                                "previous": str((self.root / "baseline.sqlite").resolve())})

    def bootstrap(self):
        return bootstrap(self.store, REPO, self.source, self.summary, self.audit,
                         "200", 2, "main", now=datetime(2026, 9, 20, tzinfo=timezone.utc))

    def test_restore_preserves_database_content(self):
        record = restore(self.store, REPO, self.out, self.receipt)
        self.assertEqual(self.source.read_bytes(), self.out.read_bytes())
        self.assertEqual(record["pointer"], POINTER)
        self.assertEqual(json.loads(self.receipt.read_text())["database"], str(self.out.resolve()))
        self.assertEqual(len(self.store.downloads), 2)

    def test_batch_pointer_requires_matching_positive_integer_field_and_asset(self):
        valid = dict(POINTER, asset="crawler-100-1-b2.sqlite.gz", batch=2)
        self.assertEqual(validate_pointer(valid, REPO), valid)
        for changes in ({"batch": True}, {"batch": 0}, {"batch": -1}, {"batch": "2"},
                        {"batch": 3}, {"asset": "crawler-100-1.sqlite.gz"}):
            with self.subTest(changes=changes), self.assertRaises(StateError):
                validate_pointer(dict(valid, **changes), REPO)
        without_batch = dict(valid)
        del without_batch["batch"]
        with self.assertRaises(StateError):
            validate_pointer(without_batch, REPO)

    def test_two_batches_keep_true_run_identity_and_distinct_immutable_assets(self):
        self.prepare_publish()
        first = self.publish(batch=1)
        receipt = json.loads(self.receipt.read_text())
        receipt["pointer"] = first
        write_json(self.receipt, receipt)
        second = self.publish(batch=2)
        self.assertEqual(first["asset"], "crawler-200-2-b1.sqlite.gz")
        self.assertEqual(second["asset"], "crawler-200-2-b2.sqlite.gz")
        self.assertEqual((first["run_id"], first["attempt"]), (second["run_id"], second["attempt"]))
        self.assertEqual(self.store.pointer["batch"], 2)
        self.assertEqual(len(self.store.uploads), 8)

    def test_invalid_batch_is_rejected_before_cloud_writes(self):
        self.prepare_publish()
        for batch in (0, -1, True, "1"):
            with self.subTest(batch=batch), self.assertRaises(StateError):
                self.publish(batch=batch)
        self.assertEqual(self.store.uploads, [])

    def test_snapshot_download_failure_never_initializes_or_publishes(self):
        self.store.fail_snapshot = True
        with self.assertRaises(StateError):
            restore(self.store, REPO, self.out, self.receipt)
        self.assertFalse(self.out.exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual(self.store.uploads, [])

    def test_corrupt_snapshot_never_becomes_state(self):
        self.store.invalid_database = True
        with self.assertRaises(StateError):
            restore(self.store, REPO, self.out, self.receipt)
        self.assertFalse(self.out.exists())

    def test_empty_database_is_rejected(self):
        with closing(sqlite3.connect(self.source)) as conn, conn:
            conn.execute("DELETE FROM crawl_works")
        with self.assertRaisesRegex(StateError, "empty"):
            restore(self.store, REPO, self.out, self.receipt)

    def test_incomplete_initialization_is_rejected(self):
        with closing(sqlite3.connect(self.source)) as conn, conn:
            conn.execute("DELETE FROM crawl_meta WHERE key='initialized'")
        with self.assertRaisesRegex(StateError, "initialization"):
            restore(self.store, REPO, self.out, self.receipt)
        self.assertFalse(self.out.exists())

    def test_missing_checkpoint_table_is_rejected(self):
        with closing(sqlite3.connect(self.source)) as conn, conn:
            conn.execute("DROP TABLE crawl_pages")
        with self.assertRaisesRegex(StateError, "checkpoint tables"):
            restore(self.store, REPO, self.out, self.receipt)
        self.assertFalse(self.out.exists())

    def test_empty_queue_is_rejected(self):
        with closing(sqlite3.connect(self.source)) as conn, conn:
            conn.execute("DELETE FROM crawl_jobs")
        with self.assertRaisesRegex(StateError, "persistent task queue"):
            restore(self.store, REPO, self.out, self.receipt)
        self.assertFalse(self.out.exists())

    def test_restore_never_overwrites_existing_database(self):
        self.out.parent.mkdir()
        self.out.write_bytes(b"keep me")
        with self.assertRaises(StateError):
            restore(self.store, REPO, self.out, self.receipt)
        self.assertEqual(self.out.read_bytes(), b"keep me")
        self.assertEqual(self.store.downloads, [])

    def test_foreign_repository_or_path_injection_is_rejected_before_snapshot_download(self):
        overrides = [
            {"source_repo": "another/owner"},
            {"tag": "../webnovel-crawler-202609"},
            {"tag": "webnovel-crawler-202613"},
            {"asset": "../../crawler-100-1.sqlite.gz"},
            {"asset": "https://example.invalid/crawler-100-1.sqlite.gz"},
            {"asset": "crawler-*.sqlite.gz"},
            {"run_id": "101"},
            {"attempt": True},
            {"schema_version": True},
            {"download_url": "https://example.invalid"},
        ]
        for changes in overrides:
            with self.subTest(changes=changes):
                self.store.pointer = dict(POINTER, **changes)
                self.store.downloads.clear()
                with self.assertRaises(StateError):
                    restore(self.store, REPO, self.out, self.receipt)
                self.assertEqual(self.store.downloads, [(POINTER_TAG, POINTER_ASSET)])
                self.assertFalse(self.out.exists())

    def test_failed_audit_blocks_all_uploads(self):
        self.prepare_publish()
        write_json(self.audit, {"passed": False, "database": str(self.out)})
        with self.assertRaisesRegex(StateError, "passing audit"):
            self.publish()
        self.assertEqual(self.store.uploads, [])

    def test_audit_of_different_database_is_rejected(self):
        self.prepare_publish()
        write_json(self.audit, {"passed": True, "database": str(self.source), "previous": str(self.source)})
        with self.assertRaisesRegex(StateError, "database being published"):
            self.publish()
        self.assertEqual(self.store.uploads, [])

    def test_each_failed_immutable_upload_leaves_pointer_unchanged(self):
        self.prepare_publish()
        for suffix in ("sqlite.gz", "summary.json", "audit.json"):
            with self.subTest(suffix=suffix):
                self.store.uploads.clear()
                self.store.assets = {POINTER_TAG: {POINTER_ASSET}, POINTER["tag"]: {POINTER["asset"]}}
                self.store.fail_asset = "crawler-200-2." + suffix
                with self.assertRaises(StateError):
                    self.publish()
                self.assertEqual(self.store.pointer, POINTER)
                self.assertFalse(any(tag == POINTER_TAG for tag, *_ in self.store.uploads))
                self.assertTrue(all(not replaced for _, _, replaced, _ in self.store.uploads))

    def test_blocked_collection_still_publishes_audited_state_pointer_last(self):
        self.prepare_publish()
        pointer = self.publish()
        self.assertEqual(pointer["asset"], "crawler-200-2.sqlite.gz")
        self.assertEqual(len(self.store.uploads), 4)
        self.assertEqual([entry[2] for entry in self.store.uploads], [False, False, False, True])
        self.assertEqual(self.store.uploads[-1][:2], (POINTER_TAG, POINTER_ASSET))
        self.assertEqual(gzip.decompress(self.store.uploads[0][3]), self.out.read_bytes())
        self.assertEqual(self.store.pointer, pointer)
        self.assertTrue(json.loads(self.store.uploads[1][3])["needs_attention"])

    def test_newer_pointer_before_publication_blocks_uploads(self):
        self.prepare_publish()
        self.store.pointer = dict(POINTER, run_id="101", asset="crawler-101-1.sqlite.gz")
        with self.assertRaisesRegex(StateError, "changed after restore"):
            self.publish()
        self.assertEqual(self.store.uploads, [])

    def test_newer_pointer_during_upload_is_not_overwritten(self):
        self.prepare_publish()
        self.store.change_after_upload = True
        with self.assertRaisesRegex(StateError, "changed during upload"):
            self.publish()
        self.assertEqual(self.store.pointer["run_id"], "101")
        self.assertEqual(len(self.store.uploads), 3)

    def test_bootstrap_publishes_snapshot_before_new_pointer_without_clobber(self):
        self.prepare_bootstrap()
        pointer = self.bootstrap()
        self.assertEqual(pointer["asset"], "crawler-200-2.sqlite.gz")
        self.assertEqual(self.store.uploads[-1][:2], (POINTER_TAG, POINTER_ASSET))
        self.assertEqual(len(self.store.uploads), 4)
        self.assertTrue(all(not replace for _, _, replace, _ in self.store.uploads))
        self.assertEqual(self.store.pointer, pointer)
        self.assertEqual(self.store.inventory_reads, 2)
        self.assertEqual(self.store.downloads, [(POINTER_TAG, POINTER_ASSET)])

    def test_bootstrap_refuses_existing_pointer_or_orphan_snapshot(self):
        for assets in ({POINTER_TAG: {POINTER_ASSET}},
                       {POINTER["tag"]: {POINTER["asset"]}},
                       {POINTER["tag"]: {"crawler-200-2.summary.json"}}):
            with self.subTest(assets=assets):
                self.prepare_bootstrap()
                self.store.assets = assets
                with self.assertRaisesRegex(StateError, "already exist"):
                    self.bootstrap()
                self.assertEqual(self.store.uploads, [])
                self.assertEqual(self.store.releases, [])

    def test_bootstrap_inventory_error_does_not_create_or_upload(self):
        self.prepare_bootstrap()
        self.store.fail_inventory = True
        with self.assertRaisesRegex(StateError, "Inventory API"):
            self.bootstrap()
        self.assertEqual(self.store.releases, [])
        self.assertEqual(self.store.uploads, [])

    def test_bootstrap_snapshot_upload_failure_never_creates_pointer(self):
        self.prepare_bootstrap()
        self.store.fail_asset = "crawler-200-2.summary.json"
        with self.assertRaisesRegex(StateError, "Upload failed"):
            self.bootstrap()
        self.assertIsNone(self.store.pointer)
        self.assertNotIn(POINTER_TAG, self.store.assets)
        self.assertFalse(any(tag == POINTER_TAG for tag, *_ in self.store.uploads))
        # The retained orphan snapshot must not be silently replaced on retry.
        self.store.fail_asset = None
        with self.assertRaisesRegex(StateError, "already exist"):
            self.bootstrap()

    def test_bootstrap_failed_audit_and_wrong_database_never_read_cloud(self):
        for report in ({"passed": False, "database": str(self.source)},
                       {"passed": True, "database": str(self.root / "different.sqlite"), "previous": "baseline.sqlite"},
                       {"passed": True, "database": str(self.source.resolve()), "previous": None}):
            with self.subTest(report=report):
                self.prepare_bootstrap()
                write_json(self.audit, report)
                with self.assertRaises(StateError):
                    self.bootstrap()
                self.assertEqual(self.store.inventory_reads, 0)
                self.assertEqual(self.store.uploads, [])

    def test_normal_publish_never_bootstraps_after_pointer_download_failure(self):
        self.prepare_publish()
        self.store.pointer = None
        self.store.assets = {}
        with self.assertRaisesRegex(StateError, "pointer download failed"):
            self.publish()
        self.assertEqual(self.store.inventory_reads, 0)
        self.assertEqual(self.store.releases, [])
        self.assertEqual(self.store.uploads, [])


class GitHubCommandTests(unittest.TestCase):
    def test_inventory_confirms_absence_only_after_successful_all_page_read(self):
        calls = []
        outputs = iter((json.dumps([[{"id": 123, "tag_name": POINTER_TAG}],
                                    [{"id": 456, "tag_name": "webnovel-crawler-202609"}]]),
                        json.dumps([[]]), json.dumps([[{"name": "crawler-200-2.sqlite.gz"}]])))
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, next(outputs), "")
        inventory = GitHubReleases(REPO, runner=runner).inventory()
        self.assertEqual(inventory, {POINTER_TAG: set(), "webnovel-crawler-202609": {"crawler-200-2.sqlite.gz"}})
        self.assertEqual(len(calls), 3)
        self.assertTrue(all("--paginate" in args and "--slurp" in args for args in calls))

    def test_inventory_error_or_malformed_json_is_never_empty_inventory(self):
        for result in (subprocess.CompletedProcess([], 1, "", "authorization failed"),
                       subprocess.CompletedProcess([], 0, "not json", ""),
                       subprocess.CompletedProcess([], 0, '{}', ""),
                       subprocess.CompletedProcess([], 0, '[[{"tag_name":"webnovel-crawler-state","id":"../../bad"}]]', "")):
            with self.subTest(result=result), self.assertRaises(StateError):
                GitHubReleases(REPO, runner=lambda *args, **kwargs: result).inventory()

    def test_read_retries_are_bounded_and_do_not_expose_stderr(self):
        calls, sleeps = [], []
        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 1, "", "HTTP 503 secret-response")
        store = GitHubReleases(REPO, runner=runner, sleeper=sleeps.append)
        with self.assertRaisesRegex(StateError, "attempts 3") as caught:
            store.command("api", "repos/owner/repo", retry_read=True)
        self.assertNotIn("secret-response", str(caught.exception))
        self.assertEqual(len(calls), 3)
        self.assertEqual(sleeps, [5, 15])
        self.assertTrue(all(kwargs["timeout"] == 120 for _, kwargs in calls))

    def test_download_retry_replaces_only_its_partial_staging_file(self):
        calls, sleeps = [], []
        def runner(args, **kwargs):
            calls.append(args)
            target = Path(args[args.index("--dir") + 1]) / POINTER_ASSET
            target.write_text("partial" if len(calls) == 1 else "complete")
            return subprocess.CompletedProcess(args, int(len(calls) == 1), "", "unexpected EOF")
        store = GitHubReleases(REPO, runner=runner, sleeper=sleeps.append)
        with tempfile.TemporaryDirectory() as tmp:
            path = store.download(POINTER_TAG, POINTER_ASSET, Path(tmp))
            self.assertEqual(path.read_text(), "complete")
            self.assertEqual(list(Path(tmp).iterdir()), [path])
            with self.assertRaisesRegex(StateError, "already exists"):
                store.download(POINTER_TAG, POINTER_ASSET, Path(tmp))
            self.assertEqual(path.read_text(), "complete")
        self.assertEqual(len(calls), 2)
        self.assertIn("--clobber", calls[0])
        self.assertEqual(sleeps, [5])

    def test_read_timeout_retries_but_failed_upload_does_not(self):
        calls, sleeps = [], []
        def runner(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(args, 120)
            return subprocess.CompletedProcess(args, 0, "ok", "")
        store = GitHubReleases(REPO, runner=runner, sleeper=sleeps.append)
        self.assertEqual(store.command("api", "test", retry_read=True), "ok")
        self.assertEqual(sleeps, [5])
        calls.clear()
        def failed(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, "", "HTTP 503")
        store.runner = failed
        with self.assertRaises(StateError):
            store.upload(POINTER_TAG, Path(POINTER_ASSET), replace=True)
        self.assertEqual(len(calls), 1)

    def test_failed_download_leaves_no_final_or_partial_file(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            (Path(args[args.index("--dir") + 1]) / POINTER_ASSET).write_text("partial")
            return subprocess.CompletedProcess(args, 1, "", "HTTP 503")
        store = GitHubReleases(REPO, runner=runner, sleeper=lambda _: None)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(StateError):
                store.download(POINTER_TAG, POINTER_ASSET, Path(tmp))
            self.assertEqual(list(Path(tmp).iterdir()), [])
        self.assertEqual(len(calls), 3)

    def test_only_pointer_upload_uses_clobber(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "", "")
        store = GitHubReleases(REPO, runner=runner)
        store.upload("webnovel-crawler-202609", Path("crawler-200-1.sqlite.gz"))
        store.upload(POINTER_TAG, Path(POINTER_ASSET), replace=True)
        self.assertNotIn("--clobber", calls[0])
        self.assertIn("--clobber", calls[1])

    def test_release_list_error_does_not_create_release(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 1, "", "authorization failed")
        store = GitHubReleases(REPO, runner=runner)
        with self.assertRaises(StateError):
            store.ensure_monthly_release("webnovel-crawler-202609", "main")
        self.assertEqual(len(calls), 1)

    def test_invalid_repository_is_rejected_without_a_command(self):
        for repo in ("../repository", "owner/repository/extra", "https://github.com/owner/repo", "-flag/repo"):
            with self.subTest(repo=repo), self.assertRaises(StateError):
                GitHubReleases(repo)


if __name__ == "__main__":
    unittest.main()
