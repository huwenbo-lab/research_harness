"""Separate isolated missing metadata from errors requiring a collection halt.

Invalid payloads remain uncommitted. Only two explicit missing-field errors
qualify for bounded rechecks and quarantine; unknown errors fail closed.
Existing events make the circuit survive restarts and alternating task kinds.
"""
from contextlib import closing
from pathlib import Path
import sqlite3


MISSING_METADATA = {
    "jjwxc_detail": "jjwxc_work_metadata_missing",
    "qidian_detail": "qidian_work_metadata_missing",
}
VALIDATION_RECHECKS = 3
CIRCUIT_WORKS = 3


def isolated_error(kind, message):
    return kind in MISSING_METADATA and message == MISSING_METADATA[kind]


def missing_attempts(conn, job):
    """Count this failure episode, excluding attempts consumed by network errors."""
    return conn.execute(
        "SELECT count(*) FROM crawl_events WHERE job_key=? AND event='failed' "
        "AND message=? AND event_id>COALESCE((SELECT max(event_id) FROM crawl_events "
        "WHERE job_key=? AND event IN ('finished','requeued')),0)",
        (job["job_key"], MISSING_METADATA[job["kind"]], job["job_key"]),
    ).fetchone()[0]


def health(conn, platforms):
    platforms = list(platforms)
    quarantined = blocking = slow_retries = 0
    circuits = []
    for platform in platforms:
        for kind, message, category in conn.execute(
                "SELECT kind,error_message,error_category FROM crawl_jobs "
                "WHERE platform=? AND status='invalid'", (platform,)):
            if category == "invalid" and isolated_error(kind, message):
                quarantined += 1
            else:
                blocking += 1
        slow_retries += conn.execute(
            "SELECT count(*) FROM crawl_jobs WHERE platform=? AND status='retry' "
            "AND failure_count>=5", (platform,)).fetchone()[0]
        for kind, reason in MISSING_METADATA.items():
            if not kind.startswith(platform + "_"):
                continue
            failures = set()
            rows = conn.execute(
                "SELECT e.job_key,e.event,e.message FROM crawl_events e "
                "JOIN crawl_jobs j ON j.job_key=e.job_key WHERE j.platform=? "
                "AND j.kind=? AND (e.event IN ('finished','requeued') "
                "OR (e.event='failed' AND e.message=?)) ORDER BY e.event_id DESC",
                (platform, kind, reason))
            for key, event, message in rows:
                if event in {"finished", "requeued"}:
                    break
                failures.add(key)
                if len(failures) >= CIRCUIT_WORKS:
                    circuits.append(kind)
                    break
    halt = bool(blocking or circuits)
    return {"halt_required": halt, "quarantined_jobs": quarantined,
            "blocking_invalid_jobs": blocking, "validation_circuits": circuits,
            "slow_retry_jobs": slow_retries,
            "needs_attention": bool(halt or quarantined or slow_retries)}


def read_health(db, platforms):
    with closing(sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        return health(conn, platforms)
