#!/usr/bin/env python3
"""One local/cloud entry point for restartable, metadata-only acquisition."""
import argparse
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import signal
import sqlite3
import sys
import tempfile
import threading
import time

from crawler_http import BudgetExhausted, Client, FetchError
from crawler_platforms import KINDS, detail_jobs, initial_catalog_jobs, run_task
from crawler_store import LeaseError, Store
from cloud_state import StateError, validate_database


def check_output_file(path, inputs=(), reject_sqlite=True):
    """Reject input aliases and database files before opening an output."""
    path = Path(path)
    for source in inputs:
        source = Path(source)
        if path.resolve() == source.resolve() or (path.exists() and source.exists() and path.samefile(source)):
            raise ValueError("output_would_overwrite_input:" + str(path))
    if reject_sqlite and path.is_file():
        with path.open("rb") as stream:
            if stream.read(16) == b"SQLite format 3\x00":
                raise ValueError("output_would_overwrite_sqlite:" + str(path))


def check_command_outputs(args):
    """Check named outputs before collection, merge, audit, or export starts."""
    inputs = [getattr(args, name, None) for name in ("db", "baseline", "live", "previous")]
    inputs = [path for path in inputs if path is not None] + list(getattr(args, "source", None) or [])
    outputs = []
    if getattr(args, "summary", None) is not None:
        outputs.append(args.summary)
    if args.command == "audit":
        outputs.append(args.out)
    for path in outputs:
        path = Path(path)
        check_output_file(path, inputs)
        check_output_file(path.with_suffix(path.suffix + ".tmp"), inputs)
    if args.command == "export":
        for name in ("crawler.sqlite", "works_current.csv", "dates_current.csv", "summary.json"):
            path = args.out / name
            # Store.export already skips its backup when this is the input DB.
            if name == "crawler.sqlite" and path.resolve() == args.db.resolve():
                continue
            check_output_file(path, inputs, reject_sqlite=name != "crawler.sqlite")


def write_json(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    # Recheck at publication too: watch may wait hours after CLI validation.
    check_output_file(path)
    check_output_file(temp)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


@contextmanager
def exclusive(path):
    """Exclude another local runner; cloud workflow also has a concurrency group."""
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another_process_is_using_this_state") from None
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def seed_jobs(store, start, end, include_works=True, platforms=None):
    current = datetime.now(timezone.utc)
    platforms = set(platforms or KINDS)

    def tasks():
        for job in initial_catalog_jobs(start, end):
            if job["platform"] not in platforms:
                continue
            # Stable historical scans continue across months. Only the current
            # catalog gets a new monthly scan; page and child tasks inherit it.
            if job["platform"] == "qidian" or job["params"].get("year") == current.year:
                job["params"]["scan"] = current.strftime("%Y-%m")
            else:
                job["params"]["scan"] = "historical-initial"
            yield job
        if include_works:
            for work in store.iter_works():
                if work["platform"] in platforms:
                    yield from detail_jobs(work["platform"], work["work_id"])

    store.enqueue_many(tasks())


def refresh_after(job, result):
    if job["kind"].endswith("catalog"):
        return None
    statuses = [str(row.get("status") or "").lower() for row in result.get("works", [])]
    complete = any(s in {"完本", "已完成", "完结", "completed", "finished"} for s in statuses)
    # Completed books change less frequently. Failed jobs use separate backoff.
    return time.time() + (90 if complete else 14) * 86400


def worker(db, platform, request_budget, seconds, stop, only_kinds=None):
    store = Store(db)
    client = Client(platform, store, max_requests=request_budget, max_seconds=seconds)
    kinds = only_kinds or KINDS[platform]
    position = 0
    invalid_streak = 0
    started = time.monotonic()
    report = {"platform": platform, "succeeded": 0, "errors": {}, "exit_reason": "no_due_tasks"}
    try:
        while not stop.is_set():
            if client.requests >= request_budget or time.monotonic() - started >= seconds:
                report["exit_reason"] = "budget_exhausted"
                break
            if store.platform_status(platform).get("blocked_until", 0) > time.time():
                report["exit_reason"] = "platform_cooldown"
                break
            job = None
            for index in range(len(kinds)):
                selected = (position + index) % len(kinds)
                job = store.claim(platform, kind=kinds[selected], lease_seconds=seconds + 120)
                if job:
                    position = (selected + 1) % len(kinds)
                    break
            if job is None:
                break
            try:
                try:
                    output = run_task(client, job)
                    store.finish(job, output, next_due=refresh_after(job, output))
                    report["succeeded"] += 1
                    invalid_streak = 0
                except BudgetExhausted:
                    store.defer(job, "request_or_time_budget")
                    report["exit_reason"] = "budget_exhausted"
                    break
                except FetchError as error:
                    store.fail(job, error.category, str(error), retry_after=error.retry_after)
                    report["errors"][error.category] = report["errors"].get(error.category, 0) + 1
                    invalid_streak = invalid_streak + 1 if error.category == "invalid" else 0
                    if error.category == "blocked":
                        report["exit_reason"] = "platform_cooldown"
                        break
                except ValueError as error:
                    # Invalid output must not advance the page cursor.
                    store.fail(job, "invalid", str(error))
                    report["errors"]["invalid"] = report["errors"].get("invalid", 0) + 1
                    invalid_streak += 1
                except LeaseError:
                    raise
                except Exception as error:
                    store.fail(job, "invalid", "internal_" + type(error).__name__)
                    report["errors"]["internal"] = report["errors"].get("internal", 0) + 1
                    report["exit_reason"] = "internal_error"
                    break
            except LeaseError:
                # Includes fail/defer after a laptop sleeps beyond its lease.
                # A later claim recovers the task without reusing this token.
                report["exit_reason"] = "lease_expired"
                break
            if invalid_streak >= 3:
                report["exit_reason"] = "repeated_validation_failure"
                break
        if stop.is_set():
            report["exit_reason"] = "interrupted"
        report["requests"] = client.requests
        report["needs_attention"] = bool(set(report["errors"]) & {"invalid", "blocked", "internal"}) or report["exit_reason"] == "platform_cooldown"
        return report
    finally:
        client.close()
        store.close()


def execution_platforms(store, requested="auto", expected_node=None):
    config = store.distribution()
    node = config["node_id"] if config else None
    if expected_node is not None and node != expected_node:
        raise ValueError("collector_node_mismatch")
    owned = config["owned_platforms"] if config else list(KINDS)
    if not owned:
        raise ValueError("coordinator_is_merge_only")
    selected = owned if requested == "auto" else list(KINDS) if requested == "both" else [requested]
    if not set(selected).issubset(owned):
        raise ValueError("requested_platform_not_assigned_to_node")
    return selected


def run(args, stop=None, manage_signals=True):
    if not args.db.is_file():
        raise FileNotFoundError("state_missing: restore a validated snapshot or explicitly run init")
    stop = stop or threading.Event()
    handlers = {}
    if manage_signals:
        for sig in (signal.SIGINT, signal.SIGTERM):
            handlers[sig] = signal.signal(sig, lambda *_: stop.set())
    try:
        with exclusive(args.db):
            validate_database(args.db)
            store = Store(args.db)
            try:
                platforms = execution_platforms(store, args.platform, getattr(args, "node", None))
                if args.kind and (len(platforms) != 1 or args.kind not in KINDS[platforms[0]]):
                    raise ValueError("--kind requires one matching platform")
                seed_jobs(store, args.start_year, args.end_year, include_works=False, platforms=platforms)
            finally:
                store.close()
            with ThreadPoolExecutor(max_workers=len(platforms)) as pool:
                futures = [pool.submit(worker, args.db, platform, args.max_requests, args.max_seconds,
                                       stop, [args.kind] if args.kind else None) for platform in platforms]
                reports = [future.result() for future in futures]
            store = Store(args.db)
            summary = store.summary()
            store.close()
            summary.update(workers=reports, needs_attention=any(r["needs_attention"] for r in reports) or any(row["status"] == "invalid" and row["platform"] in platforms for row in summary["jobs"]),
                           observed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
            if args.summary:
                write_json(args.summary, summary)
            print(json.dumps(summary, ensure_ascii=False))
            return 1 if any(r["exit_reason"] == "internal_error" for r in reports) else 0
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def watch(args):
    """Run bounded local batches until stopped; never self-repair parser errors."""
    stop = threading.Event()
    handlers = {sig: signal.signal(sig, lambda *_: stop.set()) for sig in (signal.SIGINT, signal.SIGTERM)}
    completed, last, reason = 0, None, "stopped"
    try:
        with exclusive(Path(str(args.db) + ".watch")):
            while not stop.is_set() and (not args.batches or completed < args.batches):
                # Always write the batch receipt before sleeping. It survives a
                # terminal exit and tells the user why automatic work stopped.
                code = run(args, stop=stop, manage_signals=False)
                completed += 1
                last = json.loads(args.summary.read_text(encoding="utf-8"))
                if code or any(row["status"] == "invalid" for row in last.get("owned_jobs", last["jobs"])):
                    reason = "repair_required"
                    break
                if stop.is_set():
                    break
                if args.batches and completed >= args.batches:
                    reason = "batch_limit"
                    break
                delay = args.interval
                assigned = last.get("owned_platforms", list(KINDS))
                states = [row for row in last["platforms"] if row["platform"] in assigned]
                if states and len(states) == len(assigned) and all(row["blocked"] for row in states):
                    delay = max(delay, min(row["blocked_until"] for row in states) - time.time())
                last["watch"] = {"status": "waiting", "batches_completed": completed,
                                 "next_batch_at": datetime.fromtimestamp(time.time() + delay, timezone.utc).isoformat()}
                write_json(args.summary, last)
                stop.wait(delay)
        if last is not None:
            last["watch"] = {"status": reason, "batches_completed": completed}
            write_json(args.summary, last)
        return 1 if reason == "repair_required" else 0
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)


def retry_invalid(args):
    """Explicit repair entry point; access-control cooldowns remain untouched."""
    platform = next(platform for platform, kinds in KINDS.items() if args.kind in kinds)
    with exclusive(args.db):
        validate_database(args.db)
        store = Store.open_existing(args.db)
        try:
            execution_platforms(store, platform, args.node)
            with store._transaction():
                rows = store.conn.execute("SELECT job_key,params_json FROM crawl_jobs WHERE platform=? AND kind=? AND status='invalid'", (platform, args.kind)).fetchall()
                now, changed = time.time(), 0
                for row in rows:
                    if args.work_id and json.loads(row["params_json"]).get("work_id") != args.work_id:
                        continue
                    # Explicit repairs rejoin the initial queue at their original
                    # creation position, ahead of later untouched peers.
                    store.conn.execute("UPDATE crawl_jobs SET status='pending',due_at=0,failure_count=0,error_category=NULL,error_message=NULL,token=NULL,lease_until=NULL,completed_at=NULL,updated_at=? WHERE job_key=?", (now, row["job_key"]))
                    store._event(row["job_key"], "requeued", now, "operator_repair", args.reason)
                    changed += 1
            print(json.dumps({"requeued": changed, "kind": args.kind}, ensure_ascii=False))
        finally:
            store.close()
    return 0


def quote_identifier(value):
    return '"' + value.replace('"', '""') + '"'


def audit_database(path, previous=None, expected_node=None):
    if not path.is_file():
        raise FileNotFoundError(path)
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    integrity = [r[0] for r in connection.execute("PRAGMA integrity_check")]
    fk = connection.execute("PRAGMA foreign_key_check").fetchall()
    errors = []
    try:
        _, node, _ = Store._distribution(connection)
        if expected_node is not None and node != expected_node:
            errors.append("collector_node_mismatch")
    except (ValueError, sqlite3.DatabaseError):
        errors.append("invalid_distribution_configuration")
    try:
        validate_database(path)
    except StateError as error:
        errors.append("invalid_runtime_state:" + str(error))
    if integrity != ["ok"] or fk:
        errors.append("database_integrity_or_foreign_key_failure")
    counts = {table: connection.execute("SELECT count(*) FROM " + quote_identifier(table)).fetchone()[0] for table in tables}
    if not counts.get("crawl_works"):
        errors.append("canonical_work_table_missing_or_empty")
    if "crawl_works" in tables:
        invalid = connection.execute("SELECT count(*) FROM crawl_works WHERE work_id='' OR work_id GLOB '*[^0-9]*'").fetchone()[0]
        if invalid:
            errors.append("invalid_platform_work_ids")
    comparisons = {}
    if previous:
        if not previous.is_file():
            raise FileNotFoundError("previous_database_missing")
        connection.execute("ATTACH DATABASE ? AS prior", (previous.resolve().as_uri() + "?mode=ro",))
        old_tables = [r[0] for r in connection.execute("SELECT name FROM prior.sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in old_tables:
            if table not in tables:
                errors.append("lost_table:" + table)
                continue
            if not table.startswith("crawl_") or table in {"crawl_observations", "crawl_date_evidence", "crawl_pages", "crawl_events", "crawl_conflicts", "crawl_merge_log"}:
                # Directly compare all preserved historical rows, no hashes.
                q = quote_identifier(table)
                try:
                    missing = connection.execute(f"SELECT * FROM prior.{q} EXCEPT SELECT * FROM main.{q} LIMIT 1").fetchone()
                    comparisons[table] = "preserved" if missing is None else "changed_or_missing"
                    if missing is not None:
                        errors.append("lost_historical_row:" + table)
                except sqlite3.DatabaseError:
                    errors.append("historical_schema_changed:" + table)
        for table, columns in [("crawl_chapters", "platform,work_id,chapter_key"),
                               ("crawl_jobs", "job_key"), ("crawl_work_dates", "platform,work_id,role"),
                               ("crawl_platforms", "platform")]:
            if table in old_tables and table in tables:
                lost = connection.execute(f"SELECT {columns} FROM prior.{table} EXCEPT SELECT {columns} FROM main.{table} LIMIT 1").fetchone()
                if lost:
                    errors.append("lost_record_identity:" + table)
        if "crawl_meta" in old_tables and "crawl_meta" in tables:
            lost = connection.execute("SELECT key,value FROM prior.crawl_meta WHERE key IN ('initialized','distribution_plan','node_id') EXCEPT SELECT key,value FROM main.crawl_meta").fetchone()
            if lost:
                errors.append("initialization_or_distribution_identity_changed")
        source = "crawl_works" if "crawl_works" in old_tables else "work_master"
        id_name = "work_id" if source == "crawl_works" else "platform_work_id"
        if source in old_tables and "crawl_works" in tables:
            lost = connection.execute(f"SELECT platform,{id_name} FROM prior.{source} EXCEPT SELECT platform,work_id FROM main.crawl_works").fetchall()
            comparisons["lost_work_ids"] = len(lost)
            if lost:
                errors.append("work_ids_removed")
    connection.close()
    return {"passed": not errors, "database": str(path.resolve()),
            "previous": str(previous.resolve()) if previous else None,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "integrity": integrity, "foreign_key_violations": len(fk), "counts": counts,
            "preservation": comparisons, "errors": errors}


def main():
    if sys.version_info < (3, 14):
        raise RuntimeError("Python 3.14+ is required for the tested robots matching semantics")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Explicit, one-time migration; original databases stay read-only")
    init.add_argument("--db", type=Path, required=True)
    init.add_argument("--baseline", type=Path, required=True)
    init.add_argument("--live", type=Path)
    init.add_argument("--start-year", type=int, default=2005)
    init.add_argument("--end-year", type=int, default=datetime.now().year)
    runner = commands.add_parser("run", help="Bounded batch; rerun the same command to resume")
    watcher = commands.add_parser("watch", help="Repeat bounded local batches while this process stays open")
    for command in (runner, watcher):
        command.add_argument("--db", type=Path, required=True)
        command.add_argument("--node", choices=["cloud", "local"], help="Assert this node identity; never change ownership")
        command.add_argument("--platform", choices=["auto", "both", "qidian", "jjwxc"], default="auto")
        command.add_argument("--kind", choices=[k for kinds in KINDS.values() for k in kinds])
        command.add_argument("--max-requests", type=int, default=50, help="Per-platform budget including robots and session pages")
        command.add_argument("--max-seconds", type=int, default=300)
        command.add_argument("--start-year", type=int, default=2005)
        command.add_argument("--end-year", type=int, default=datetime.now().year)
        command.add_argument("--summary", type=Path)
    watcher.add_argument("--interval", type=int, default=1800, help="Seconds to wait between local batches")
    watcher.add_argument("--batches", type=int, default=0, help="0 continues until stopped; a positive count runs finitely")
    splitter = commands.add_parser("split", help="Make a fixed cloud/local collection plan and a merge-only coordinator")
    splitter.add_argument("--db", type=Path, required=True)
    splitter.add_argument("--out", type=Path, required=True)
    merger = commands.add_parser("merge", help="Idempotently merge node observations into the coordinator")
    merger.add_argument("--db", type=Path, required=True)
    merger.add_argument("--source", type=Path, required=True, action="append")
    merger.add_argument("--summary", type=Path)
    repair = commands.add_parser("retry-invalid", help="Explicitly requeue invalid results after fixing their cause")
    repair.add_argument("--db", type=Path, required=True)
    repair.add_argument("--node", choices=["cloud", "local"])
    repair.add_argument("--kind", required=True, choices=[k for kinds in KINDS.values() for k in kinds])
    repair.add_argument("--work-id")
    repair.add_argument("--reason", required=True)
    status = commands.add_parser("status")
    status.add_argument("--db", type=Path, required=True)
    export = commands.add_parser("export")
    export.add_argument("--db", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    audit = commands.add_parser("audit")
    audit.add_argument("--db", type=Path, required=True)
    audit.add_argument("--previous", type=Path)
    audit.add_argument("--node", choices=["cloud", "local", "coordinator"])
    audit.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # Resolve the DB itself before deriving either lock name. Appending .watch
    # first would leave a symlink to the database with a different outer lock.
    args.db = args.db.resolve()
    if args.command in {"run", "watch", "init"} and not 2003 <= args.start_year <= args.end_year <= datetime.now().year:
        parser.error("invalid year range")
    if args.command in {"run", "watch"} and not (1 <= args.max_requests <= 2000 and 1 <= args.max_seconds <= 86400):
        parser.error("invalid bounded run budget")
    if args.command == "watch" and (args.interval < 1 or args.batches < 0):
        parser.error("invalid watch interval or batch count")
    if args.command == "watch":
        args.summary = args.summary or args.db.parent / (args.db.stem + "_watch_summary.json")
    check_command_outputs(args)
    if args.command == "audit":
        result = audit_database(args.db, args.previous, args.node)
        write_json(args.out, result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["passed"] else 1
    if args.command == "run":
        return run(args)
    if args.command == "watch":
        return watch(args)
    if args.command == "split":
        from crawler_sync import split_state
        # A watch process retains its outer lock while sleeping between batches.
        with exclusive(Path(str(args.db) + ".watch")):
            with exclusive(args.db):
                manifest = split_state(args.db, args.out)
        print(json.dumps(manifest, ensure_ascii=False))
        return 0
    if args.command == "merge":
        from crawler_sync import merge_state
        with exclusive(args.db):
            receipts = [merge_state(args.db, source) for source in args.source]
        result = {"merges": receipts, "summary": Store.read_summary(args.db)}
        if args.summary:
            write_json(args.summary, result)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.command == "retry-invalid":
        return retry_invalid(args)
    if args.command == "status":
        print(json.dumps(Store.read_summary(args.db), ensure_ascii=False))
        return 0
    if args.command != "init" and not args.db.is_file():
        raise FileNotFoundError("state_missing")
    with exclusive(args.db):
        if args.command == "init" and args.db.exists():
            raise FileExistsError("initialization_refuses_existing_state")
        if args.command != "init":
            validate_database(args.db)
        staging = None
        if args.command == "init":
            args.db.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix=args.db.name + ".init.", dir=args.db.parent, delete=False) as handle:
                staging = Path(handle.name)
        store = Store(staging or args.db)
        try:
            if args.command == "init":
                store.bootstrap(args.baseline, args.live)
                seed_jobs(store, args.start_year, args.end_year)
            elif args.command == "export":
                store.export(args.out)
            summary = store.summary()
        except BaseException:
            store.close()
            if staging:
                staging.unlink(missing_ok=True)
            raise
        finally:
            store.close()
        if staging:
            staging.replace(args.db)
        print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
