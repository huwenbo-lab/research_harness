"""Split a shared snapshot by platform and merge immutable observations.

Callers must hold the runner's exclusive source lock while splitting and its
exclusive target lock while merging. Source databases are always read-only;
network access and remote job-state synchronization are deliberately absent.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from itertools import zip_longest
import json
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
import time
import uuid

from cloud_state import validate_database
from crawler_store import Store, canonical


ASSIGNMENTS = {"cloud": ["qidian"], "local": ["jjwxc"]}
NODES = ("coordinator", "cloud", "local")
MERGE_SCHEMA = """CREATE TABLE IF NOT EXISTS crawl_merge_log(
 merge_id TEXT PRIMARY KEY, plan_id TEXT NOT NULL, source_node TEXT NOT NULL,
 source_path TEXT NOT NULL, merged_at TEXT NOT NULL,
 imported_observations INTEGER NOT NULL, known_observations INTEGER NOT NULL,
 source_observations INTEGER NOT NULL, source_queue_json TEXT NOT NULL,
 source_platforms_json TEXT NOT NULL
)"""


class SyncError(ValueError):
    """Inputs do not establish a safe split or merge."""


def _utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _quote(value):
    return '"' + value.replace('"', '""') + '"'


def _snapshot(source: Path, destination: Path):
    """Pin one read transaction and create a standalone SQLite backup."""
    if not source.is_file():
        raise FileNotFoundError(source)
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as incoming:
        incoming.execute("PRAGMA query_only=ON")
        incoming.execute("BEGIN")
        incoming.execute("SELECT count(*) FROM sqlite_master").fetchone()
        with closing(sqlite3.connect(destination)) as outgoing:
            incoming.backup(outgoing)


def _meta(conn, key, schema="main"):
    row = conn.execute(f"SELECT value FROM {schema}.crawl_meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _plan(conn, schema="main"):
    try:
        plan = json.loads(_meta(conn, "distribution_plan", schema))
    except (TypeError, ValueError) as exc:
        raise SyncError("distribution_plan_missing_or_invalid") from exc
    if (not isinstance(plan, dict)
            or set(plan) != {"schema_version", "plan_id", "assignments", "created_at"}
            or type(plan["schema_version"]) is not int or plan["schema_version"] != 1
            or not isinstance(plan["plan_id"], str)
            or not re.fullmatch(r"[0-9a-f]{32}", plan["plan_id"])
            or plan["assignments"] != ASSIGNMENTS):
        raise SyncError("distribution_plan_invalid")
    try:
        stamp = datetime.fromisoformat(plan["created_at"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None:
            raise ValueError("timezone_missing")
    except (TypeError, ValueError, AttributeError) as exc:
        raise SyncError("distribution_plan_created_at_invalid") from exc
    return plan


def split_state(source: Path, out: Path) -> dict:
    """Prepare all three role databases before atomically exposing the directory.

    Existing output paths and an already distributed source are refused. The
    original database, its task states, and its research data are never changed.
    """
    source, out = Path(source).resolve(), Path(out).absolute()
    if out.exists() or out.is_symlink():
        raise FileExistsError(out)
    if not out.parent.is_dir():
        raise FileNotFoundError(out.parent)
    plan = {"schema_version": 1, "plan_id": uuid.uuid4().hex,
            "assignments": {key: list(value) for key, value in ASSIGNMENTS.items()}, "created_at": _utc()}
    manifest = {"schema_version": 1, "distribution_plan": plan, "source": str(source),
                "nodes": {node: str(out / (node + ".sqlite")) for node in NODES}}
    with tempfile.TemporaryDirectory(prefix="." + out.name + ".split-", dir=out.parent) as tmp:
        stage = Path(tmp)
        coordinator = stage / "coordinator.sqlite"
        _snapshot(source, coordinator)
        validate_database(coordinator)
        with closing(sqlite3.connect(coordinator)) as conn:
            if _meta(conn, "distribution_plan") is not None or _meta(conn, "node_id") is not None:
                raise SyncError("source_already_distributed")
            if conn.execute("SELECT 1 FROM crawl_jobs WHERE status='leased' AND (lease_until IS NULL OR lease_until>?) LIMIT 1", (time.time(),)).fetchone():
                raise SyncError("source_has_active_lease")
            conn.execute("INSERT INTO crawl_meta VALUES('distribution_plan',?)", (canonical(plan),))
            conn.execute("INSERT INTO crawl_meta VALUES('node_id','coordinator')")
            conn.commit()
        for node in ("cloud", "local"):
            node_path = stage / (node + ".sqlite")
            shutil.copyfile(coordinator, node_path)
            with closing(sqlite3.connect(node_path)) as conn:
                conn.execute("UPDATE crawl_meta SET value=? WHERE key='node_id'", (node,))
                conn.commit()
        for node in NODES:
            validate_database(stage / (node + ".sqlite"))
        (stage / "plan.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Refuse an output created while snapshots were being prepared.
        if out.exists() or out.is_symlink():
            raise FileExistsError(out)
        stage.rename(out)
    return manifest


def _legacy_tables(conn, schema):
    return {row[0]: row[1] for row in conn.execute(
        f"SELECT name,sql FROM {schema}.sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' AND substr(name,1,6)<>'crawl_' ORDER BY name")}


def _compare_history(conn):
    """Compare actual typed rows, including duplicates, without digests."""
    initialized = _meta(conn, "initialized")
    if not initialized or initialized != _meta(conn, "initialized", "incoming"):
        raise SyncError("initialization_identity_mismatch")
    tables = _legacy_tables(conn, "main")
    if tables != _legacy_tables(conn, "incoming") or "work_master" not in tables:
        raise SyncError("historical_table_schema_mismatch")
    sentinel = object()
    for table in tables:
        quoted = _quote(table)
        columns = [row[1] for row in conn.execute(f"PRAGMA main.table_info({quoted})")]
        order = ",".join(f"typeof({_quote(col)}),{_quote(col)} COLLATE BINARY" for col in columns)
        left = conn.execute(f"SELECT * FROM main.{quoted} ORDER BY {order}")
        right = conn.execute(f"SELECT * FROM incoming.{quoted} ORDER BY {order}")
        for a, b in zip_longest(left, right, fillvalue=sentinel):
            if a is sentinel or b is sentinel or len(a) != len(b) or any(type(x) is not type(y) or x != y for x, y in zip(a, b)):
                raise SyncError("historical_rows_mismatch:" + table)
    return len(tables)


def _source_status(conn):
    queue = [dict(row) for row in conn.execute(
        "SELECT platform,kind,status,count(*) AS count FROM incoming.crawl_jobs "
        "GROUP BY platform,kind,status ORDER BY platform,kind,status")]
    platforms = [dict(row) for row in conn.execute("SELECT * FROM incoming.crawl_platforms ORDER BY platform")]
    return queue, platforms


def _validate_new_observation(row, source_node, plan):
    if not isinstance(row["observation_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", row["observation_id"]):
        raise SyncError("new_observation_uuid_invalid")
    try:
        result = json.loads(row["result_json"])
        meta = result["meta"]
    except (TypeError, ValueError, KeyError) as exc:
        raise SyncError("new_observation_metadata_invalid") from exc
    if (not isinstance(meta, dict) or meta.get("collector_node") != source_node
            or meta.get("collection_plan") != plan["plan_id"]):
        raise SyncError("new_observation_node_or_plan_mismatch")
    if row["platform"] not in plan["assignments"][source_node]:
        raise SyncError("new_observation_platform_not_assigned")


def merge_state(target: Path, source: Path) -> dict:
    """Merge only observations; commit their derived data and audit as one unit.

    Node queues, leases, cooldowns and request reservations are diagnostics, not
    transferable execution state. Older source snapshots are valid and harmless.
    """
    target, source = Path(target).resolve(), Path(source).resolve()
    if target == source:
        raise SyncError("merge_requires_distinct_databases")
    validate_database(target)
    with tempfile.TemporaryDirectory(prefix="webnovel-merge-") as tmp:
        snapshot = Path(tmp) / "source.sqlite"
        _snapshot(source, snapshot)
        validate_database(snapshot)
        store = Store.open_existing(target)
        try:
            conn = store.conn
            conn.execute("ATTACH DATABASE ? AS incoming", (snapshot.as_uri() + "?mode=ro",))
            conn.execute("BEGIN IMMEDIATE")
            try:
                plan = _plan(conn)
                if _meta(conn, "node_id") != "coordinator":
                    raise SyncError("merge_target_must_be_coordinator")
                source_node = _meta(conn, "node_id", "incoming")
                if source_node not in ASSIGNMENTS:
                    raise SyncError("merge_source_must_be_collector")
                if _plan(conn, "incoming") != plan:
                    raise SyncError("distribution_plan_mismatch")
                historical_tables = _compare_history(conn)
                queue, platforms = _source_status(conn)
                imported = known = 0
                for row in conn.execute("SELECT * FROM incoming.crawl_observations ORDER BY observed_ts,observation_id"):
                    previous = conn.execute("SELECT * FROM main.crawl_observations WHERE observation_id=?", (row["observation_id"],)).fetchone()
                    if previous is not None:
                        if dict(previous) != dict(row):
                            raise SyncError("observation_id_payload_mismatch:" + row["observation_id"])
                        known += 1
                        continue
                    _validate_new_observation(row, source_node, plan)
                    if not store.import_observation(dict(row)):
                        raise SyncError("unexpected_duplicate_observation")
                    imported += 1
                report = {"merge_id": uuid.uuid4().hex, "plan_id": plan["plan_id"],
                          "source_node": source_node, "source_path": str(source), "merged_at": _utc(),
                          "imported_observations": imported, "known_observations": known,
                          "source_observations": imported + known, "historical_tables_compared": historical_tables,
                          "source_queue": queue, "source_platforms": platforms,
                          "target_queue_semantics": "logical_tasks_not_remote_execution_progress"}
                conn.execute(MERGE_SCHEMA)
                conn.execute("INSERT INTO crawl_merge_log VALUES(?,?,?,?,?,?,?,?,?,?)", (
                    report["merge_id"], plan["plan_id"], source_node, str(source), report["merged_at"],
                    imported, known, imported + known, canonical(queue), canonical(platforms)))
                conn.commit()
                return report
            except BaseException:
                conn.rollback()
                raise
        finally:
            store.close()
