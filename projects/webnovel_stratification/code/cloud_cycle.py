"""Run up to three small cloud-node batches, publishing each before continuing."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zlib

from cloud_state import (GitHubReleases, StateError, bootstrap, publish, read_json,
                         require_uninitialized, restore, validate_database,
                         validate_repository, write_json)
from crawler_health import read_health
from crawler_store import Store


BOOTSTRAP_TAG = "webnovel-crawler-bootstrap"
BOOTSTRAP_ASSET_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}\.sqlite\.gz")


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    write_json(temporary, value)
    temporary.replace(path)


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source, temporary)
    temporary.replace(destination)


def bootstrap_from_staging(store, repo: str, out: Path, source_asset: str,
                           previous_asset: str, run_id: str, attempt: int,
                           target: str, execute) -> dict:
    """First start only, using two explicit assets from this repository's fixed tag."""
    validate_repository(repo)
    for name in (source_asset, previous_asset):
        if (not isinstance(name, str) or not BOOTSTRAP_ASSET_PATTERN.fullmatch(name)
                or ".." in name):
            raise StateError("Bootstrap assets must be individual .sqlite.gz filenames, not paths or URLs")
    if source_asset == previous_asset:
        raise StateError("Bootstrap source and predecessor must be separate assets")
    # Check before downloading, and bootstrap checks again immediately before
    # publishing. Missing or unreadable state is never treated as permission to reset.
    require_uninitialized(store)
    directory = out / "bootstrap"
    directory.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix=".source-", dir=directory) as tmp:
        stage = Path(tmp)
        source, previous = stage / "cloud.sqlite", stage / "previous.sqlite"
        for asset, database in ((source_asset, source), (previous_asset, previous)):
            compressed = store.download(BOOTSTRAP_TAG, asset, stage)
            try:
                with gzip.open(compressed, "rb") as incoming, database.open("wb") as destination:
                    shutil.copyfileobj(incoming, destination)
            except (OSError, EOFError, zlib.error) as exc:
                raise StateError("Could not decompress a bootstrap asset; no state was initialized") from exc
            validate_database(database)
        audit = directory / "audit.json"
        if execute("audit", "--db", source, "--previous", previous,
                   "--node", "cloud", "--out", audit) != 0:
            raise StateError("Bootstrap cloud-node preservation audit failed; no state was initialized")
        report = read_json(audit)
        if (report.get("passed") is not True
                or report.get("database") != str(source.resolve())
                or report.get("previous") != str(previous.resolve())):
            raise StateError("Bootstrap audit did not verify the downloaded source and predecessor")
        summary = directory / "summary.json"
        atomic_json(summary, {"node_id": "cloud", "run_id": run_id, "attempt": attempt,
                              "needs_attention": False, "counts": report.get("counts", {}),
                              "bootstrap_source": {"source_repo": repo, "tag": BOOTSTRAP_TAG,
                                                   "source_asset": source_asset,
                                                   "previous_asset": previous_asset}})
        pointer = bootstrap(store, repo, source, summary, audit, run_id, attempt, target)
        atomic_json(directory / "pointer.json", pointer)
        return pointer


def run_cycle(store, repo: str, db: Path, out: Path, run_id: str, attempt: int,
              target: str, batches: int = 3, max_requests: int = 50,
              max_seconds: int = 300, run_command=None,
              bootstrap_source_asset: str | None = None,
              bootstrap_previous_asset: str | None = None) -> dict:
    if not (1 <= batches <= 3 and 1 <= max_requests <= 50 and 1 <= max_seconds <= 300):
        raise StateError("Cloud cycle permits 1-3 batches of at most 50 requests and 300 seconds")
    command = run_command or (lambda args: subprocess.run(args, check=False).returncode)
    entry = Path(__file__).with_name("crawl.py")
    receipt = db.parent / "restored.json"
    previous = db.parent / "previous.sqlite"

    def execute(operation, *args):
        return command([sys.executable, str(entry), operation, *map(str, args)])

    if bool(bootstrap_source_asset) != bool(bootstrap_previous_asset):
        raise StateError("Bootstrap requires both source and predecessor asset names")
    initial_pointer = None
    if bootstrap_source_asset:
        if db.exists() or receipt.exists():
            raise StateError("Bootstrap requires new local restore destinations")
        initial_pointer = bootstrap_from_staging(
            store, repo, out, bootstrap_source_asset, bootstrap_previous_asset,
            run_id, attempt, target, execute)
    restore(store, repo, db, receipt)
    out.mkdir(parents=True, exist_ok=True)
    restored_audit = out / "restored_audit.json"
    if execute("audit", "--db", db, "--node", "cloud", "--out", restored_audit) != 0:
        raise StateError("Restored cloud-node audit failed; collection did not start")
    if read_json(restored_audit).get("passed") is not True:
        raise StateError("Restored cloud-node audit did not pass")
    result = {"node_id": "cloud", "run_id": run_id, "attempt": attempt,
              "completed_batches": [], "needs_attention": False, "halt_required": False}
    if initial_pointer is not None:
        result["bootstrap_pointer"] = initial_pointer
    summary_path = out / "cloud_summary.json"
    # Apply the current research scope before checking inherited invalid tasks.
    # A retired chapter request must not block valid work-level acquisition.
    state = Store.open_existing(db)
    try:
        state.apply_endpoint_scope()
    finally:
        state.close()
    restored_summary = Store.read_summary(db)
    invalid_jobs = [group for group in restored_summary["owned_jobs"] if group["status"] == "invalid"]
    result.update(read_health(db, restored_summary["owned_platforms"]))
    if result["halt_required"]:
        result.update(needs_attention=True, exit_reason="repair_required", invalid_jobs=invalid_jobs)
        atomic_json(summary_path, result)
        return result
    atomic_copy(db, previous)
    atomic_json(summary_path, result)

    batch = 0
    try:
        for batch in range(1, batches + 1):
            directory = out / f"batch-{batch}"
            directory.mkdir(parents=True, exist_ok=True)
            run_summary = directory / "run_summary.json"
            return_code = execute("run", "--db", db, "--node", "cloud",
                                  "--max-requests", max_requests, "--max-seconds", max_seconds,
                                  "--summary", run_summary)
            # Unexpected collection errors may still have durable queue progress.
            # Audit and retain that progress before stopping the cycle for attention.
            try:
                run_report = read_json(run_summary)
            except StateError:
                run_report = {"needs_attention": True, "halt_required": True,
                              "exit_reason": "missing_or_invalid_run_summary"}
            workers = run_report.get("workers", [])
            invalid_summary = (not isinstance(workers, list) or not workers
                               or any(not isinstance(worker, dict) or not isinstance(worker.get("errors", {}), dict)
                                      for worker in workers)
                               or ("halt_required" in run_report and not isinstance(run_report["halt_required"], bool)))
            interrupted = any(worker.get("exit_reason") == "interrupted"
                              for worker in workers if isinstance(worker, dict)) if isinstance(workers, list) else False
            worker_failure = any(worker.get("exit_reason") in {"platform_cooldown", "repeated_validation_failure",
                                                               "validation_halted", "internal_error"}
                                 or any(worker.get("errors", {}).get(key) for key in ("internal", "blocked"))
                                 for worker in workers) if not invalid_summary else True
            halt_required = (return_code != 0 or interrupted or worker_failure or invalid_summary
                             or bool(run_report.get("halt_required", run_report.get("needs_attention"))))
            health = read_health(db, restored_summary["owned_platforms"])
            halt_required = halt_required or health["halt_required"]
            needs_attention = halt_required or bool(run_report.get("needs_attention")) or health["needs_attention"]
            export = directory / "export"
            if execute("export", "--db", db, "--out", export) != 0:
                raise StateError(f"Batch {batch} export failed; cycle stopped before publication")
            snapshot = export / "crawler.sqlite"
            audit = directory / "audit.json"
            if execute("audit", "--db", snapshot, "--previous", previous,
                       "--node", "cloud", "--out", audit) != 0:
                raise StateError(f"Batch {batch} audit failed; cycle stopped before publication")
            cloud_summary = directory / "cloud_summary.json"
            report = {"node_id": "cloud", "run_id": run_id, "attempt": attempt,
                      "batch": batch, "run": run_report, "export": read_json(export / "summary.json"),
                      **health, "needs_attention": needs_attention, "halt_required": halt_required}
            atomic_json(cloud_summary, report)
            pointer = publish(store, repo, snapshot, cloud_summary, audit, receipt,
                              run_id, attempt, target, batch=batch)
            # Only a verified publication advances the next batch's lineage. If the
            # runner dies here, the next GitHub run restores the new remote pointer.
            atomic_json(receipt, {"schema_version": 1, "source_repo": repo,
                                  "pointer": pointer, "database": str(db.resolve())})
            atomic_copy(snapshot, previous)
            result["completed_batches"].append({"batch": batch, "pointer": pointer,
                                                 "needs_attention": needs_attention,
                                                 "halt_required": halt_required})
            result.update({key: value for key, value in health.items() if key != "needs_attention"})
            result["needs_attention"] = result["needs_attention"] or needs_attention
            result["halt_required"] = halt_required
            atomic_json(summary_path, result)
            if halt_required:
                break
            if workers and all(isinstance(worker, dict) and worker.get("exit_reason") == "no_due_tasks"
                               and not worker.get("errors")
                               for worker in workers):
                break
    except (StateError, OSError) as error:
        result.update(needs_attention=True, halt_required=True, failed_batch=batch, error=str(error))
        atomic_json(summary_path, result)
        raise
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--attempt", type=int, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--db", type=Path, default=Path("state/crawler.sqlite"))
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--batches", type=int, default=3)
    parser.add_argument("--max-requests", type=int, default=50)
    parser.add_argument("--max-seconds", type=int, default=300)
    parser.add_argument("--bootstrap-source-asset",
                        help=f"Explicit first start only: source .sqlite.gz asset in {BOOTSTRAP_TAG}")
    parser.add_argument("--bootstrap-previous-asset",
                        help="The separate .sqlite.gz predecessor in the same fixed staging release")
    args = parser.parse_args()
    try:
        result = run_cycle(GitHubReleases(args.repo), args.repo, args.db, args.out,
                           args.run_id, args.attempt, args.target, args.batches,
                           args.max_requests, args.max_seconds,
                           bootstrap_source_asset=args.bootstrap_source_asset,
                           bootstrap_previous_asset=args.bootstrap_previous_asset)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result["halt_required"] else 0
    except (StateError, OSError) as exc:
        parser.exit(1, f"cloud cycle stopped: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
