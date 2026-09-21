"""Durable crawl jobs, immutable observations, and rebuildable current metadata.

The original v0.4 tables are copied without alteration during bootstrap. All new
tables use the crawl_ prefix. Identities are readable strings; no checksums are
computed. A result, its follow-up jobs, and its lease acknowledgement commit as
one transaction.
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


class LeaseError(RuntimeError):
    """The worker no longer owns an unexpired lease."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _clock(now=None):
    value = time.time() if now is None else float(now)
    if not math.isfinite(value):
        raise ValueError("time must be finite")
    return value


def _iso(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="microseconds")


def _timestamp(value):
    if isinstance(value, (int, float)):
        return _clock(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _same_date_value(left, right):
    """Compare full timestamps at equal precision; platform local time is UTC+08.

    Dates, years, minute precision, and different fractional-second precision
    remain distinct evidence. This does not alter raw or stored date strings.
    """
    left, right = str(left), str(right)
    if left == right:
        return True
    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?"
    matches = [re.fullmatch(pattern, value) for value in (left, right)]
    if any(match is None for match in matches):
        return False
    if len(matches[0].group(1) or "") != len(matches[1].group(1) or ""):
        return False
    parsed = []
    for value in (left, right):
        try:
            date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
        parsed.append(date if date.tzinfo is not None else date.replace(tzinfo=timezone(timedelta(hours=8))))
    return parsed[0] == parsed[1]


def _nonempty(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _first(row, *keys):
    return next((row[k] for k in keys if _nonempty(row.get(k))), None)


DATE_ROLES = {
    "catalog_pub_date": "catalog_publication",
    "platform_declared_pub_date": "catalog_publication",
    "platform_catalog_publication": "catalog_publication",
    "platform_reported_publication_date": "platform_publication",
    "first_chapter_publication_date": "first_chapter_publication",
    "last_chapter_publication_date": "last_chapter_publication",
    "last_update_date": "last_update",
    "last_update_date_observed": "last_update",
    "last_chapter_update_date": "last_update",
    "latest_chapter_update_date": "last_update",
    "completion_date_candidate": "completion_candidate",
}

# These legacy candidate rows describe individual chapters. Keeping one of their
# values in a work-level role would manufacture both a work date and conflicts.
EVIDENCE_ONLY_DATE_ROLES = frozenset({
    "chapter_publication", "chapter_publication_tooltip", "chapter_update",
})

UNRESOLVED_COVERAGE = frozenset({
    "api_cap_unresolved", "page_limit_unresolved", "partitioned_unverified",
    "unresolved", "partial", "public_html_partial",
})

OBSERVATION_COLUMNS = (
    "observation_id", "job_key", "platform", "kind", "source_kind", "source_url",
    "observed_at", "observed_ts", "recorded_at", "time_basis", "coverage", "result_json",
)
NODE_PLATFORMS = {"cloud": ["qidian"], "local": ["jjwxc"]}


SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS crawl_jobs(
 job_key TEXT PRIMARY KEY, platform TEXT NOT NULL, kind TEXT NOT NULL,
 params_json TEXT NOT NULL, priority INTEGER NOT NULL, due_at REAL NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', token TEXT, lease_until REAL,
 attempts INTEGER NOT NULL DEFAULT 0, failure_count INTEGER NOT NULL DEFAULT 0,
 created_at REAL NOT NULL, updated_at REAL NOT NULL, completed_at REAL,
 error_category TEXT, error_message TEXT
);
CREATE INDEX IF NOT EXISTS crawl_jobs_due ON crawl_jobs(platform,status,due_at,priority);
CREATE TABLE IF NOT EXISTS crawl_platforms(
 platform TEXT PRIMARY KEY, blocked_until REAL NOT NULL DEFAULT 0,
 next_request_at REAL NOT NULL DEFAULT 0, blocked_reason TEXT, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS crawl_events(
 event_id INTEGER PRIMARY KEY, job_key TEXT NOT NULL, event TEXT NOT NULL,
 category TEXT, message TEXT, at REAL NOT NULL,
 FOREIGN KEY(job_key) REFERENCES crawl_jobs(job_key)
);
CREATE TABLE IF NOT EXISTS crawl_observations(
 observation_id TEXT PRIMARY KEY, job_key TEXT, platform TEXT NOT NULL,
 kind TEXT NOT NULL, source_kind TEXT NOT NULL, source_url TEXT,
 observed_at TEXT, observed_ts REAL NOT NULL, recorded_at REAL NOT NULL,
 time_basis TEXT NOT NULL, coverage TEXT, result_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS crawl_observations_job ON crawl_observations(job_key,recorded_at);
CREATE TABLE IF NOT EXISTS crawl_works(
 platform TEXT NOT NULL, work_id TEXT NOT NULL,
 title TEXT, author TEXT, genre TEXT, status TEXT, work_url TEXT,
 catalog_pub_year INTEGER, sample_class TEXT,
 metadata_json TEXT NOT NULL, field_times_json TEXT NOT NULL,
 first_observed_at TEXT, last_observed_at TEXT, last_observed_ts REAL NOT NULL,
 source_kind TEXT NOT NULL, observation_id TEXT NOT NULL,
 PRIMARY KEY(platform,work_id)
);
CREATE TABLE IF NOT EXISTS crawl_work_dates(
 platform TEXT NOT NULL, work_id TEXT NOT NULL, role TEXT NOT NULL,
 value TEXT NOT NULL, basis TEXT, source_url TEXT,
 observed_at TEXT, observed_ts REAL NOT NULL, source_kind TEXT NOT NULL,
 observation_id TEXT NOT NULL, PRIMARY KEY(platform,work_id,role),
 FOREIGN KEY(platform,work_id) REFERENCES crawl_works(platform,work_id)
);
CREATE TABLE IF NOT EXISTS crawl_date_evidence(
 evidence_id INTEGER PRIMARY KEY, observation_id TEXT NOT NULL,
 platform TEXT NOT NULL, work_id TEXT NOT NULL, role TEXT NOT NULL,
 value TEXT NOT NULL, basis TEXT, source_url TEXT,
 observed_at TEXT, source_kind TEXT NOT NULL, raw_json TEXT NOT NULL,
 FOREIGN KEY(observation_id) REFERENCES crawl_observations(observation_id)
);
CREATE TABLE IF NOT EXISTS crawl_chapters(
 platform TEXT NOT NULL, work_id TEXT NOT NULL, chapter_key TEXT NOT NULL,
 chapter_id TEXT, chapter_title TEXT, chapter_url TEXT, publication_date TEXT,
 update_date TEXT, is_vip INTEGER, word_count TEXT, chapter_number TEXT,
 metadata_json TEXT NOT NULL, field_times_json TEXT NOT NULL,
 observed_at TEXT, observed_ts REAL NOT NULL, source_kind TEXT NOT NULL,
 observation_id TEXT NOT NULL, PRIMARY KEY(platform,work_id,chapter_key),
 FOREIGN KEY(platform,work_id) REFERENCES crawl_works(platform,work_id)
);
CREATE TABLE IF NOT EXISTS crawl_pages(
 observation_id TEXT PRIMARY KEY, platform TEXT NOT NULL,
 partition_key TEXT NOT NULL, page INTEGER NOT NULL, page_ids_json TEXT NOT NULL,
 coverage TEXT, FOREIGN KEY(observation_id) REFERENCES crawl_observations(observation_id)
);
CREATE INDEX IF NOT EXISTS crawl_pages_partition ON crawl_pages(platform,partition_key,page);
CREATE TABLE IF NOT EXISTS crawl_conflicts(
 conflict_id INTEGER PRIMARY KEY, platform TEXT NOT NULL, work_id TEXT NOT NULL,
 entity TEXT NOT NULL, entity_key TEXT NOT NULL, field TEXT NOT NULL,
 kept_value_json TEXT NOT NULL, incoming_value_json TEXT NOT NULL,
 observed_ts REAL NOT NULL, observation_id TEXT NOT NULL,
 FOREIGN KEY(observation_id) REFERENCES crawl_observations(observation_id)
);
"""


class Store:
    MAX_FAILURES = 5
    MAX_BACKOFF = 86400

    def __init__(self, path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = self._connect(self.path)
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if ("work_master" in tables or "works" in tables) and "crawl_meta" not in tables:
            self.conn.close()
            raise ValueError("open a separate state path; import source databases with bootstrap")
        self.conn.executescript(SCHEMA)

    @staticmethod
    def _connect(path):
        conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    @classmethod
    def open_existing(cls, path):
        """Open existing writable state without creating or migrating schema."""
        database = Path(path).resolve()
        if not database.is_file():
            raise FileNotFoundError(database)
        conn = sqlite3.connect(database.as_uri() + "?mode=rw", uri=True,
                               timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            required = {"crawl_meta", "crawl_jobs", "crawl_platforms", "crawl_events",
                        "crawl_observations", "crawl_works", "crawl_work_dates",
                        "crawl_date_evidence", "crawl_chapters", "crawl_pages", "crawl_conflicts"}
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            columns = tuple(row[1] for row in conn.execute("PRAGMA table_info(crawl_observations)"))
            if not required.issubset(tables) or columns != OBSERVATION_COLUMNS:
                raise ValueError("not a compatible crawler state database")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")
        except BaseException:
            conn.close()
            raise
        instance = cls.__new__(cls)
        instance.path, instance.conn = str(database), conn
        return instance

    @contextmanager
    def _transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.conn.commit()
        except BaseException:
            self.conn.rollback()
            raise

    @staticmethod
    def _job_key(platform, kind, params):
        if not isinstance(platform, str) or not platform or not isinstance(kind, str) or not kind:
            raise ValueError("platform and kind are required")
        if not isinstance(params, dict):
            raise ValueError("params must be an object")
        if platform not in {"qidian", "jjwxc"}:
            raise ValueError("unsupported platform")
        return canonical([platform, kind, params])

    def _enqueue(self, platform, kind, params, priority, due_at, now):
        key = self._job_key(platform, kind, params)
        self.conn.execute(
            "INSERT OR IGNORE INTO crawl_jobs(job_key,platform,kind,params_json,priority,due_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            (key, platform, kind, canonical(params), int(priority), _clock(due_at), now, now),
        )
        return key

    def enqueue(self, platform, kind, params, priority=100, due_at=0):
        with self._transaction():
            return self._enqueue(platform, kind, params, priority, due_at, _clock())

    def enqueue_many(self, jobs):
        with self._transaction():
            now = _clock()
            before = self.conn.total_changes
            for job in jobs:
                self._enqueue(job["platform"], job["kind"], job["params"], job.get("priority", 100), job.get("due_at", 0), now)
            return self.conn.total_changes - before

    def claim(self, platform, kind=None, now=None, lease_seconds=300):
        now = _clock(now)
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        with self._transaction():
            self._require_owned_platform(platform)
            self.conn.execute(
                "UPDATE crawl_jobs SET status='retry',token=NULL,lease_until=NULL,due_at=?,updated_at=? WHERE platform=? AND status='leased' AND lease_until<=?",
                (now, now, platform, now),
            )
            if self.platform_status(platform, now)["blocked_until"] > now:
                return None
            query = "SELECT * FROM crawl_jobs WHERE platform=? AND status IN ('pending','retry','blocked') AND due_at<=?"
            params = [platform, now]
            if kind is not None:
                query += " AND kind=?"
                params.append(kind)
            row = self.conn.execute(query + " ORDER BY priority,due_at,created_at,job_key LIMIT 1", params).fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            self.conn.execute(
                "UPDATE crawl_jobs SET status='leased',token=?,lease_until=?,attempts=attempts+1,updated_at=? WHERE job_key=?",
                (token, now + lease_seconds, now, row["job_key"]),
            )
            self._event(row["job_key"], "claimed", now)
            return {"job_key": row["job_key"], "platform": row["platform"], "kind": row["kind"],
                    "params": json.loads(row["params_json"]), "token": token, "attempts": row["attempts"] + 1}

    def _lease(self, job, now):
        row = self.conn.execute("SELECT * FROM crawl_jobs WHERE job_key=?", (job.get("job_key"),)).fetchone()
        if (row is None or row["status"] != "leased" or not job.get("token")
                or row["token"] != job["token"] or row["lease_until"] <= now
                or row["platform"] != job.get("platform") or row["kind"] != job.get("kind")):
            raise LeaseError("lease expired, completed, or owned by another worker")
        return row

    def _event(self, key, event, now, category=None, message=None):
        self.conn.execute("INSERT INTO crawl_events(job_key,event,category,message,at) VALUES(?,?,?,?,?)", (key, event, category, message, now))

    def finish(self, job, result, next_due=None, now=None):
        now = _clock(now)
        with self._transaction():
            row = self._lease(job, now)
            observation = self._record_result(row["platform"], row["kind"], result, now, job_key=row["job_key"])
            coverage = result.get("meta", {}).get("coverage")
            status = "done" if next_due is None else "pending"
            if coverage == "budget_exhausted":
                status = "pending"
            elif coverage in UNRESOLVED_COVERAGE:
                status = "unresolved"
            self.conn.execute(
                "UPDATE crawl_jobs SET status=?,due_at=?,token=NULL,lease_until=NULL,failure_count=0,completed_at=?,updated_at=?,error_category=NULL,error_message=NULL WHERE job_key=?",
                (status, now if next_due is None else _clock(next_due), now if status == "done" else None, now, row["job_key"]),
            )
            self._event(row["job_key"], "finished", now)
            return observation

    def fail(self, job, category, message="", retry_after=0, now=None):
        now = _clock(now)
        aliases = {"transient": "retry", "network": "retry", "retryable": "retry", "parse_error": "invalid"}
        category = aliases.get(category, category)
        if category not in {"retry", "blocked", "gone", "invalid"}:
            raise ValueError("unknown failure category")
        with self._transaction():
            row = self._lease(job, now)
            count = row["failure_count"] + 1
            delay = max(0, float(retry_after))
            status = category
            if category == "retry":
                delay = max(delay, min(self.MAX_BACKOFF, 30 * 2 ** min(count - 1, 12)))
                if count >= self.MAX_FAILURES:
                    status = "invalid"
            elif category == "blocked":
                delay = max(delay, 3600)
                self._block_platform(row["platform"], message or category, delay, now)
            due = now + delay
            self.conn.execute(
                "UPDATE crawl_jobs SET status=?,due_at=?,token=NULL,lease_until=NULL,failure_count=?,updated_at=?,error_category=?,error_message=? WHERE job_key=?",
                (status, due, count, now, category, message, row["job_key"]),
            )
            self._event(row["job_key"], "failed", now, category, message)
            return status

    def defer(self, job, reason, now=None):
        now = _clock(now)
        with self._transaction():
            row = self._lease(job, now)
            self.conn.execute("UPDATE crawl_jobs SET status='pending',due_at=?,token=NULL,lease_until=NULL,updated_at=? WHERE job_key=?", (now, now, row["job_key"]))
            self._event(row["job_key"], "deferred", now, "budget", reason)
            return "pending"

    def platform_status(self, platform, now=None):
        now = _clock(now)
        row = self.conn.execute("SELECT * FROM crawl_platforms WHERE platform=?", (platform,)).fetchone()
        result = dict(row) if row else {"platform": platform, "blocked_until": 0, "next_request_at": 0, "blocked_reason": None, "updated_at": 0}
        result["blocked"] = result["blocked_until"] > now
        return result

    def reserve_request(self, platform, delay, now=None):
        now = _clock(now)
        delay = float(delay)
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("delay must be finite and nonnegative")
        with self._transaction():
            state = self.platform_status(platform, now)
            slot = max(now, state["next_request_at"], state["blocked_until"])
            self.conn.execute(
                "INSERT INTO crawl_platforms(platform,next_request_at,updated_at) VALUES(?,?,?) ON CONFLICT(platform) DO UPDATE SET next_request_at=excluded.next_request_at,updated_at=excluded.updated_at",
                (platform, slot + delay, now),
            )
            return slot - now

    def _block_platform(self, platform, reason, seconds, now):
        until = now + max(0, float(seconds))
        self.conn.execute(
            "INSERT INTO crawl_platforms(platform,blocked_until,blocked_reason,updated_at) VALUES(?,?,?,?) ON CONFLICT(platform) DO UPDATE SET blocked_until=MAX(crawl_platforms.blocked_until,excluded.blocked_until),blocked_reason=excluded.blocked_reason,updated_at=excluded.updated_at",
            (platform, until, reason, now),
        )

    def block_platform(self, platform, reason, seconds, now=None):
        with self._transaction():
            self._block_platform(platform, reason, seconds, _clock(now))

    @staticmethod
    def _wid(row):
        value = _first(row, "work_id", "platform_work_id", "book_id")
        if value is None or not re.fullmatch(r"[0-9]+", str(value).strip()):
            raise ValueError("work_id must contain ASCII digits only")
        return str(value).strip()

    def _conflict(self, platform, wid, entity, key, field, kept, incoming, stamp, observation):
        self.conn.execute("INSERT INTO crawl_conflicts(platform,work_id,entity,entity_key,field,kept_value_json,incoming_value_json,observed_ts,observation_id) VALUES(?,?,?,?,?,?,?,?,?)", (platform, wid, entity, key, field, canonical(kept), canonical(incoming), stamp, observation))

    def _merge(self, previous, times, incoming, stamp, platform, wid, entity, entity_key, observation):
        for key, value in incoming.items():
            if _nonempty(value) and (not _nonempty(previous.get(key)) or stamp > times.get(key, float("-inf"))):
                previous[key] = value
                times[key] = stamp
            elif _nonempty(value) and stamp == times.get(key) and canonical(value) != canonical(previous.get(key)):
                self._conflict(platform, wid, entity, entity_key, key, previous[key], value, stamp, observation)
        return previous, times

    def _work(self, platform, row, obs):
        wid = self._wid(row)
        old = self.conn.execute("SELECT * FROM crawl_works WHERE platform=? AND work_id=?", (platform, wid)).fetchone()
        values = json.loads(old["metadata_json"]) if old else {}
        times = json.loads(old["field_times_json"]) if old else {}
        incoming = {k: v for k, v in row.items() if k not in {"platform", "work_id", "platform_work_id", "book_id", "observed_at"}}
        incoming.update(title=row.get("title"), author=_first(row, "author", "author_name_current"),
                        genre=_first(row, "genre_raw", "genre", "category"), status=_first(row, "status", "status_raw"),
                        work_url=_first(row, "work_url", "source_url", "url"),
                        catalog_pub_year=_first(row, "catalog_pub_year", "declared_pub_year", "platform_declared_pub_year"))
        if _nonempty(row.get("sample_class")):
            incoming["sample_class_basis"] = "explicit"
        values, times = self._merge(values, times, incoming, obs["observed_ts"], platform, wid, "work", wid, obs["observation_id"])
        if values.get("sample_class_basis") != "explicit":
            genre = values.get("genre")
            values["sample_class"] = "non_novel" if genre in {"评论", "诗歌", "随笔"} else "novel_like" if isinstance(genre, str) and "-" in genre else "unresolved"
            values["sample_class_basis"] = "genre_observation"
            times["sample_class"] = times.get("genre", obs["observed_ts"])
            times["sample_class_basis"] = times["sample_class"]
        newer = old is None or obs["observed_ts"] > old["last_observed_ts"]
        source = obs if newer else {"observed_at": old["last_observed_at"], "observed_ts": old["last_observed_ts"], "source_kind": old["source_kind"], "observation_id": old["observation_id"]}
        first = old["first_observed_at"] if old else None
        if obs["observed_at"] and (not first or obs["observed_ts"] < _timestamp(first)):
            first = obs["observed_at"]
        cols = ("title", "author", "genre", "status", "work_url", "catalog_pub_year", "sample_class")
        self.conn.execute(
            "INSERT INTO crawl_works VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,work_id) DO UPDATE SET title=excluded.title,author=excluded.author,genre=excluded.genre,status=excluded.status,work_url=excluded.work_url,catalog_pub_year=excluded.catalog_pub_year,sample_class=excluded.sample_class,metadata_json=excluded.metadata_json,field_times_json=excluded.field_times_json,first_observed_at=excluded.first_observed_at,last_observed_at=excluded.last_observed_at,last_observed_ts=excluded.last_observed_ts,source_kind=excluded.source_kind,observation_id=excluded.observation_id",
            (platform, wid, *(values.get(k) for k in cols), canonical(values), canonical(times), first, source["observed_at"], source["observed_ts"], source["source_kind"], source["observation_id"]),
        )
        return wid

    def _date(self, platform, row, obs):
        wid = self._wid(row)
        original_role = row.get("role")
        if not isinstance(original_role, str) or not original_role:
            raise ValueError("date role and value are required")
        role = DATE_ROLES.get(original_role, original_role)
        value = row.get("value")
        if type(value) not in (str, int, float) or (isinstance(value, float) and not math.isfinite(value)):
            raise ValueError("date value must be a string or finite number")
        if not _nonempty(value):
            raise ValueError("date role and value are required")
        if not self.conn.execute("SELECT 1 FROM crawl_works WHERE platform=? AND work_id=?", (platform, wid)).fetchone():
            self._work(platform, {"work_id": wid}, obs)
        basis = row.get("basis")
        basis = canonical(basis) if isinstance(basis, (dict, list)) else basis
        url = row.get("source_url") or obs.get("source_url")
        self.conn.execute("INSERT INTO crawl_date_evidence(observation_id,platform,work_id,role,value,basis,source_url,observed_at,source_kind,raw_json) VALUES(?,?,?,?,?,?,?,?,?,?)", (obs["observation_id"], platform, wid, role, str(value), basis, url, obs["observed_at"], obs["source_kind"], canonical(row)))
        if role in EVIDENCE_ONLY_DATE_ROLES:
            return
        old = self.conn.execute("SELECT value,observed_ts FROM crawl_work_dates WHERE platform=? AND work_id=? AND role=?", (platform, wid, role)).fetchone()
        equivalent = old is not None and _same_date_value(old["value"], value)
        if old and old["observed_ts"] == obs["observed_ts"] and not equivalent:
            self._conflict(platform, wid, "date", role, "value", old["value"], str(value), obs["observed_ts"], obs["observation_id"])
        current_value = old["value"] if equivalent else str(value)
        self.conn.execute(
            "INSERT INTO crawl_work_dates VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,work_id,role) DO UPDATE SET value=excluded.value,basis=excluded.basis,source_url=excluded.source_url,observed_at=excluded.observed_at,observed_ts=excluded.observed_ts,source_kind=excluded.source_kind,observation_id=excluded.observation_id WHERE excluded.observed_ts>crawl_work_dates.observed_ts",
            (platform, wid, role, current_value, basis, url, obs["observed_at"], obs["observed_ts"], obs["source_kind"], obs["observation_id"]),
        )

    def _chapter(self, platform, row, obs):
        wid = self._wid(row)
        cid = _first(row, "chapter_id", "chapter_number", "chapter_number_raw", "chapter_key")
        if cid is not None and type(cid) not in (str, int):
            raise ValueError("chapter identity must be a string or integer")
        title = row.get("chapter_title")
        url = _first(row, "chapter_url", "url")
        if cid is None and not title and not url:
            raise ValueError("chapter identity is missing")
        key = "id:" + str(cid) if cid is not None else "title_url:" + canonical([title, url])
        if not self.conn.execute("SELECT 1 FROM crawl_works WHERE platform=? AND work_id=?", (platform, wid)).fetchone():
            self._work(platform, {"work_id": wid}, obs)
        old = self.conn.execute("SELECT * FROM crawl_chapters WHERE platform=? AND work_id=? AND chapter_key=?", (platform, wid, key)).fetchone()
        values = json.loads(old["metadata_json"]) if old else {}
        times = json.loads(old["field_times_json"]) if old else {}
        incoming = dict(row)
        incoming.update(chapter_id=str(cid) if cid is not None else None, chapter_url=url,
                        publication_date=_first(row, "publication_date", "publish_time", "publish_time_as_supplied", "date_published"),
                        update_date=_first(row, "update_date", "update_time", "update_time_as_supplied", "display_time", "date_modified"),
                        is_vip=_first(row, "is_vip", "vip", "is_vip_as_supplied"),
                        word_count=_first(row, "word_count", "word_count_raw"),
                        chapter_number=_first(row, "chapter_number", "chapter_number_raw"))
        vip = incoming.get("is_vip")
        if vip is not None:
            incoming["is_vip"] = {"true": 1, "false": 0, "1": 1, "0": 0}.get(str(vip).lower())
        values, times = self._merge(values, times, incoming, obs["observed_ts"], platform, wid, "chapter", key, obs["observation_id"])
        newer = old is None or obs["observed_ts"] > old["observed_ts"]
        source = obs if newer else dict(old)
        cols = ("chapter_id", "chapter_title", "chapter_url", "publication_date", "update_date", "is_vip", "word_count", "chapter_number")
        self.conn.execute(
            "INSERT INTO crawl_chapters VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(platform,work_id,chapter_key) DO UPDATE SET chapter_id=excluded.chapter_id,chapter_title=excluded.chapter_title,chapter_url=excluded.chapter_url,publication_date=excluded.publication_date,update_date=excluded.update_date,is_vip=excluded.is_vip,word_count=excluded.word_count,chapter_number=excluded.chapter_number,metadata_json=excluded.metadata_json,field_times_json=excluded.field_times_json,observed_at=excluded.observed_at,observed_ts=excluded.observed_ts,source_kind=excluded.source_kind,observation_id=excluded.observation_id",
            (platform, wid, key, *(values.get(k) for k in cols), canonical(values), canonical(times), source["observed_at"], source["observed_ts"], source["source_kind"], source["observation_id"]),
        )

    @staticmethod
    def _distribution(conn):
        settings = dict(conn.execute("SELECT key,value FROM crawl_meta WHERE key IN ('distribution_plan','node_id')"))
        if not settings:
            return None, None, ["qidian", "jjwxc"]
        if set(settings) != {"distribution_plan", "node_id"}:
            raise ValueError("incomplete distribution configuration")
        try:
            plan = json.loads(settings["distribution_plan"])
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid distribution plan") from exc
        node = settings["node_id"]
        if (not isinstance(plan, dict) or set(plan) != {"schema_version", "plan_id", "assignments", "created_at"}
                or type(plan.get("schema_version")) is not int
                or plan["schema_version"] != 1 or plan.get("assignments") != NODE_PLATFORMS
                or not isinstance(plan.get("plan_id"), str)
                or not re.fullmatch(r"[0-9a-f]{32}", plan["plan_id"])
                or node not in {*NODE_PLATFORMS, "coordinator"}
                or not isinstance(plan.get("created_at"), str)):
            raise ValueError("invalid distribution plan or node")
        try:
            stamp = datetime.fromisoformat(plan["created_at"].replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError("timezone_missing")
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValueError("invalid distribution creation time") from exc
        return plan, node, list(NODE_PLATFORMS.get(node, []))

    def _require_owned_platform(self, platform):
        plan, node, owned = self._distribution(self.conn)
        if platform not in owned:
            raise ValueError("platform not assigned to collector node: " + str(platform))
        return plan, node

    def distribution(self):
        """Return validated node configuration, or None for standalone state."""
        plan, node, owned = self._distribution(self.conn)
        return {"plan": plan, "node_id": node, "owned_platforms": owned} if plan is not None else None

    @staticmethod
    def _validate_result(platform, result):
        if platform not in {"qidian", "jjwxc"}:
            raise ValueError("unsupported platform")
        if not isinstance(result, dict) or not isinstance(result.get("meta", {}), dict):
            raise ValueError("result and meta must be objects")
        for key in ("works", "dates", "chapters", "followups"):
            if not isinstance(result.get(key, []), list):
                raise ValueError(key + " must be a list")
            for row in result.get(key, []):
                if not isinstance(row, dict) or row.get("platform", platform) != platform:
                    raise ValueError("row platform mismatch or invalid row")
                if key == "followups":
                    Store._job_key(platform, row["kind"], row["params"])
                    if any(row["kind"].startswith(other + "_") for other in ("qidian", "jjwxc") if other != platform):
                        raise ValueError("followup kind platform mismatch")
                    int(row.get("priority", 100))
                    _clock(row.get("due_at", 0))
        if result.get("platform", platform) != platform or result.get("meta", {}).get("platform", platform) != platform:
            raise ValueError("result platform mismatch")
        canonical(result)

    def _validate_collector(self, platform, meta):
        plan, _, _ = self._distribution(self.conn)
        node, plan_id = meta.get("collector_node"), meta.get("collection_plan")
        if node is None and plan_id is None:
            return
        if (not isinstance(node, str) or node not in NODE_PLATFORMS or platform not in NODE_PLATFORMS[node]
                or not isinstance(plan_id, str) or not re.fullmatch(r"[0-9a-f]{32}", plan_id)):
            raise ValueError("invalid observation collector provenance")
        if plan is not None and plan_id != plan["plan_id"]:
            raise ValueError("observation collection plan mismatch")

    def _record_result(self, platform, kind, result, now, job_key=None, source_kind=None, import_stamp=None):
        self._validate_result(platform, result)
        if import_stamp is None:
            plan, node = self._require_owned_platform(platform)
            meta = result.get("meta", {})
            if plan is not None:
                for key, value in (("collector_node", node), ("collection_plan", plan["plan_id"])):
                    if key in meta and meta[key] != value:
                        raise ValueError("result collector provenance mismatch")
                result = {**result, "meta": {**meta, "collector_node": node, "collection_plan": plan["plan_id"]}}
            self._validate_collector(platform, result.get("meta", {}))
        raw = canonical(result)
        meta = result.get("meta", {})
        stamp = meta.get("observed_at")
        if import_stamp is not None:
            observed_at, observed_ts, time_basis = None, import_stamp, "legacy_snapshot_time_unknown"
        elif stamp is not None:
            observed_ts = _timestamp(stamp)
            observed_at, time_basis = _iso(observed_ts), "reported_observed_at"
        else:
            observed_at, observed_ts, time_basis = _iso(now), now, "result_received_at_fallback"
        obs = {"observation_id": uuid.uuid4().hex, "job_key": job_key, "platform": platform, "kind": kind,
               "source_kind": source_kind or meta.get("source_kind") or kind, "source_url": meta.get("source_url"),
               "observed_at": observed_at, "observed_ts": observed_ts, "recorded_at": now,
               "time_basis": time_basis, "coverage": meta.get("coverage"), "result_json": raw}
        self._apply_observation(obs, result, now)
        return obs["observation_id"]

    def _apply_observation(self, obs, result, now):
        platform = obs["platform"]
        meta = result.get("meta", {})
        ids = meta.get("page_ids", [])
        if not isinstance(ids, list):
            raise ValueError("page_ids must be a list")
        partition = meta.get("partition_key")
        page = meta.get("page")
        if ids and partition is not None and page is not None:
            ids_json = canonical([str(x) for x in ids])
            partition = partition if isinstance(partition, str) else canonical(partition)
            repeated = self.conn.execute("SELECT 1 FROM crawl_pages WHERE platform=? AND partition_key=? AND page<>? AND page_ids_json=? LIMIT 1", (platform, partition, int(page), ids_json)).fetchone()
            if repeated:
                raise ValueError("repeated_catalog_page")
        self.conn.execute("INSERT INTO crawl_observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", tuple(obs[key] for key in OBSERVATION_COLUMNS))
        if partition is not None and page is not None:
            partition = partition if isinstance(partition, str) else canonical(partition)
            self.conn.execute("INSERT INTO crawl_pages VALUES(?,?,?,?,?,?)", (obs["observation_id"], platform, partition, int(page), canonical([str(x) for x in ids]), meta.get("coverage")))
        for row in result.get("works", []):
            self._work(platform, row, obs)
        for row in result.get("dates", []):
            self._date(platform, row, obs)
        for row in result.get("chapters", []):
            self._chapter(platform, row, obs)
        for follow in result.get("followups", []):
            self._enqueue(follow.get("platform", platform), follow["kind"], follow["params"], follow.get("priority", 100), follow.get("due_at", 0), now)

    def import_observation(self, row):
        """Replay an immutable source row inside the caller's transaction.

        Remote job leases and completion state are never imported. The savepoint
        isolates a rejected row without committing or rolling back its caller.
        """
        if not self.conn.in_transaction:
            raise ValueError("import_observation requires an external transaction")
        obs = dict(row)
        if set(obs) != set(OBSERVATION_COLUMNS):
            raise ValueError("observation row must contain all original columns")
        existing = self.conn.execute("SELECT * FROM crawl_observations WHERE observation_id=?", (obs["observation_id"],)).fetchone()
        if existing is not None:
            if all(existing[key] == obs[key] for key in OBSERVATION_COLUMNS):
                return False
            raise ValueError("observation_id has different content")
        for key in ("observation_id", "platform", "kind", "source_kind", "time_basis", "result_json"):
            if not isinstance(obs[key], str) or not obs[key]:
                raise ValueError("invalid observation " + key)
        for key in ("source_url", "coverage", "observed_at", "job_key"):
            if obs[key] is not None and not isinstance(obs[key], str):
                raise ValueError("invalid observation " + key)
        for key in ("observed_ts", "recorded_at"):
            if type(obs[key]) not in (int, float) or not math.isfinite(obs[key]):
                raise ValueError("invalid observation " + key)
        try:
            def unique_object(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("duplicate JSON key")
                    result[key] = value
                return result
            result = json.loads(obs["result_json"], object_pairs_hook=unique_object)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid observation JSON") from exc
        self._validate_result(obs["platform"], result)
        meta = result.get("meta", {})
        self._validate_collector(obs["platform"], meta)
        if obs["source_url"] != meta.get("source_url") or obs["coverage"] != meta.get("coverage"):
            raise ValueError("observation metadata mismatch")
        if "source_kind" in meta and obs["source_kind"] != meta["source_kind"]:
            raise ValueError("observation source kind mismatch")
        if obs["job_key"] is not None:
            try:
                key = json.loads(obs["job_key"])
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid observation job key") from exc
            if not isinstance(key, list) or len(key) != 3 or key[:2] != [obs["platform"], obs["kind"]] or not isinstance(key[2], dict):
                raise ValueError("observation job identity mismatch")
        basis = obs["time_basis"]
        if basis == "legacy_snapshot_time_unknown":
            expected = {"imported_baseline_v04": -2, "imported_live": -1}.get(obs["source_kind"])
            if obs["observed_at"] is not None or meta.get("observed_at") is not None or expected is None or obs["observed_ts"] != expected:
                raise ValueError("invalid legacy observation time")
        elif basis in {"reported_observed_at", "result_received_at_fallback"}:
            if obs["observed_at"] is None or not math.isclose(_timestamp(obs["observed_at"]), obs["observed_ts"], rel_tol=0, abs_tol=1e-6):
                raise ValueError("observation timestamp mismatch")
            if basis == "reported_observed_at":
                if meta.get("observed_at") is None or not math.isclose(_timestamp(meta["observed_at"]), obs["observed_ts"], rel_tol=0, abs_tol=1e-6):
                    raise ValueError("payload observation timestamp mismatch")
            elif meta.get("observed_at") is not None or obs["observed_ts"] != obs["recorded_at"]:
                raise ValueError("fallback observation timestamp mismatch")
        else:
            raise ValueError("unknown observation time basis")
        self.conn.execute("SAVEPOINT import_observation")
        try:
            self._apply_observation(obs, result, _clock())
            self.conn.execute("RELEASE SAVEPOINT import_observation")
        except BaseException:
            self.conn.execute("ROLLBACK TO SAVEPOINT import_observation")
            self.conn.execute("RELEASE SAVEPOINT import_observation")
            raise
        return True

    def iter_works(self):
        for row in self.conn.execute("SELECT * FROM crawl_works ORDER BY platform,work_id"):
            yield self._decode_work(row)

    @staticmethod
    def _decode_work(row):
        result = json.loads(row["metadata_json"])
        result["metadata"] = dict(result)
        result.update({k: row[k] for k in row.keys() if k not in {"metadata_json", "field_times_json"}})
        return result

    def get_work(self, platform, work_id):
        row = self.conn.execute("SELECT * FROM crawl_works WHERE platform=? AND work_id=?", (platform, str(work_id))).fetchone()
        return self._decode_work(row) if row else None

    def bootstrap(self, baseline_path, live_path=None):
        """Stage a full baseline backup, import metadata, then replace self.conn.

        Legacy timestamps are retained in raw/extra metadata, but are not claimed
        as fresh retrieval times. Baseline < live snapshot < actual observations.
        """
        if self.conn.execute("SELECT 1 FROM crawl_meta WHERE key='initialized'").fetchone():
            raise ValueError("store is already initialized")
        if any(self.conn.execute("SELECT 1 FROM " + table + " LIMIT 1").fetchone() for table in ("crawl_jobs", "crawl_observations", "crawl_works")):
            raise ValueError("bootstrap requires an empty store")
        baseline = Path(baseline_path).resolve()
        if not baseline.is_file():
            raise FileNotFoundError(baseline)
        live = Path(live_path).resolve() if live_path is not None else None
        if live is not None and not live.is_file():
            raise FileNotFoundError(live)
        if self.path != ":memory:" and Path(self.path).resolve() in {baseline, live}:
            raise ValueError("state must differ from the read-only input databases")
        stage_path = ":memory:" if self.path == ":memory:" else str(Path(self.path).with_name("." + Path(self.path).name + ".bootstrap-" + uuid.uuid4().hex + ".tmp"))
        old_conn = self.conn
        stage = self._connect(stage_path)
        source = None
        try:
            source = sqlite3.connect(baseline.as_uri() + "?mode=ro", uri=True)
            source.execute("PRAGMA query_only=ON")
            if source.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'crawl_%'").fetchone():
                raise ValueError("baseline must not already contain crawl state")
            source.backup(stage)
            source.close()
            source = None
            stage.executescript(SCHEMA)
            self.conn = stage
            with self._transaction():
                self._import_baseline()
                if live is not None:
                    self._import_live(live)
                if self.conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise ValueError("bootstrap integrity check failed")
                self.conn.execute("INSERT INTO crawl_meta VALUES('initialized',?)", (_iso(time.time()),))
                self.conn.execute("INSERT INTO crawl_meta VALUES('baseline_path',?)", (str(baseline),))
                if live is not None:
                    self.conn.execute("INSERT INTO crawl_meta VALUES('live_path',?)", (str(live),))
            if self.path == ":memory:":
                old_conn.close()
            else:
                stage.close()
                os.replace(stage_path, self.path)
                old_conn.close()
                self.conn = self._connect(self.path)
        except BaseException:
            if source is not None:
                source.close()
            stage.close()
            self.conn = old_conn
            if stage_path != ":memory:":
                Path(stage_path).unlink(missing_ok=True)
            raise
        return self.summary()

    def _import_batches(self, rows, section, source_kind, table, stamp):
        groups = {}
        for platform, item in rows:
            groups.setdefault(platform, []).append(item)
            if len(groups[platform]) >= 500:
                self._record_result(platform, "bootstrap", {section: groups.pop(platform), "meta": {"legacy_table": table}}, time.time(), source_kind=source_kind, import_stamp=stamp)
        for platform, items in groups.items():
            self._record_result(platform, "bootstrap", {section: items, "meta": {"legacy_table": table}}, time.time(), source_kind=source_kind, import_stamp=stamp)

    def _import_baseline(self):
        tables = {x[0] for x in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "work_master" not in tables:
            raise ValueError("baseline work_master table missing")
        identities = {}
        def works():
            for raw in self.conn.execute("SELECT * FROM work_master"):
                row = dict(raw)
                platform, wid = row["platform"], str(row["platform_work_id"])
                identities[row.get("work_key", platform + ":" + wid)] = (platform, wid)
                yield platform, {**row, "work_id": wid}
        self._import_batches(works(), "works", "imported_baseline_v04", "work_master", -2)
        def identity(row):
            return identities.get(row.get("work_key"))
        if "work_dates" in tables:
            excluded = {"work_key", "completion_status_observed", "ending_date_basis", "chapter_time_conflict", "catalog_vs_chapter_pub_year_conflict", "notes"}
            def dates():
                for raw in self.conn.execute("SELECT * FROM work_dates"):
                    row = dict(raw)
                    key = identity(row)
                    if not key:
                        continue
                    for role, value in row.items():
                        if role not in excluded and _nonempty(value):
                            yield key[0], {"work_id": key[1], "role": role, "value": value, "basis": "baseline work_dates." + role, "legacy_notes": row.get("notes"), "legacy_ending_basis": row.get("ending_date_basis")}
            self._import_batches(dates(), "dates", "imported_baseline_v04", "work_dates", -2)
        for table, value_key, role_key in (("date_evidence", "date_raw", "date_role"), ("date_candidate", "date_value", "date_role")):
            if table not in tables:
                continue
            def evidence(table=table, value_key=value_key, role_key=role_key):
                for raw in self.conn.execute("SELECT * FROM " + table):
                    row = dict(raw)
                    key = identity(row)
                    if key and _nonempty(row.get(value_key)):
                        yield key[0], {**row, "work_id": key[1], "role": row[role_key], "value": row[value_key], "basis": table + "." + role_key}
            self._import_batches(evidence(), "dates", "imported_baseline_v04", table, -2)
        if "chapter_metadata" in tables:
            def chapters():
                for raw in self.conn.execute("SELECT * FROM chapter_metadata"):
                    row = dict(raw)
                    key = identity(row)
                    if key and any(_nonempty(row.get(k)) for k in ("chapter_id", "chapter_number_raw", "chapter_title", "chapter_url")):
                        yield key[0], {**row, "work_id": key[1]}
            self._import_batches(chapters(), "chapters", "imported_baseline_v04", "chapter_metadata", -2)

    def _import_live(self, path):
        source = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        source.row_factory = sqlite3.Row
        source.execute("PRAGMA query_only=ON")
        try:
            tables = {x[0] for x in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "works" not in tables:
                raise ValueError("live works table missing")
            self._import_batches(((row["platform"], dict(row)) for row in source.execute("SELECT * FROM works")), "works", "imported_live", "works", -1)
            if "work_dates" in tables:
                def dates():
                    for raw in source.execute("SELECT * FROM work_dates"):
                        row = dict(raw)
                        for role, value in row.items():
                            if role not in {"platform", "work_id", "publication_date_basis", "completion_date_basis", "date_observed_at"} and _nonempty(value):
                                basis = row.get("completion_date_basis") if role == "completion_date_candidate" else row.get("publication_date_basis") if role == "platform_reported_publication_date" else "live work_dates." + role
                                yield row["platform"], {"work_id": row["work_id"], "role": role, "value": value, "basis": basis, "legacy_date_observed_at": row.get("date_observed_at")}
                self._import_batches(dates(), "dates", "imported_live", "work_dates", -1)
            if "chapters" in tables:
                self._import_batches(((row["platform"], dict(row)) for row in source.execute("SELECT * FROM chapters")), "chapters", "imported_live", "chapters", -1)
        finally:
            source.close()

    def apply_endpoint_scope(self, platforms=None):
        """Replace full chapter tasks with bounded date endpoints; preserve history."""
        config = self.distribution()
        platforms = platforms if platforms is not None else (config["owned_platforms"] if config else ["qidian", "jjwxc"])
        changed, now = 0, _clock()
        with self._transaction():
            if "qidian" in platforms:
                rows = self.conn.execute("SELECT job_key,status,lease_until,params_json,priority,due_at FROM crawl_jobs WHERE platform='qidian' AND kind='qidian_chapters' AND status IN ('pending','retry','blocked','invalid','leased','excluded')").fetchall()
                if any(row["status"] == "leased" and (row["lease_until"] is None or row["lease_until"] > now) for row in rows):
                    raise ValueError("chapter_worker_still_running")
                for row in rows:
                    if row["status"] != "excluded":
                        self.conn.execute("UPDATE crawl_jobs SET status='excluded',token=NULL,lease_until=NULL,updated_at=? WHERE job_key=?", (now, row["job_key"]))
                        self._event(row["job_key"], "excluded", now, "collection_scope", "replaced_by_date_endpoints")
                        changed += 1
                    self._enqueue("qidian", "qidian_dates", json.loads(row["params_json"]), row["priority"], row["due_at"], now)
            self.conn.execute("INSERT OR REPLACE INTO crawl_meta(key,value) VALUES('collection_scope','work_date_endpoints')")
        return changed

    @classmethod
    def read_summary(cls, path):
        """Read one committed snapshot without opening a writable Store."""
        database = Path(path).resolve()
        if not database.is_file():
            raise FileNotFoundError(database)
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True,
                               timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("BEGIN")
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='crawl_meta'").fetchone():
                raise ValueError("not a crawler state database")
            return cls._summarize(conn)
        finally:
            conn.close()

    def summary(self, _conn=None):
        return self._summarize(self.conn if _conn is None else _conn)

    @staticmethod
    def _summarize(conn):
        plan, node, owned = Store._distribution(conn)
        count = lambda table: conn.execute("SELECT count(*) FROM " + table).fetchone()[0]
        jobs = [dict(r) for r in conn.execute("SELECT platform,kind,status,count(*) AS count FROM crawl_jobs GROUP BY platform,kind,status ORDER BY platform,kind,status")]
        counts = {"works": count("crawl_works"), "dates": count("crawl_work_dates"), "date_evidence": count("crawl_date_evidence"), "chapters": count("crawl_chapters"), "observations": count("crawl_observations"), "jobs": count("crawl_jobs"), "conflicts": count("crawl_conflicts")}
        unresolved_labels = sorted(UNRESOLVED_COVERAGE | {"budget_exhausted"})
        placeholders = ",".join("?" for _ in unresolved_labels)
        # Synchronization can insert older observations after newer ones.
        unresolved = conn.execute("SELECT count(DISTINCT job_key) FROM crawl_observations o WHERE job_key IS NOT NULL AND coverage IN (" + placeholders + ") AND observation_id=(SELECT observation_id FROM crawl_observations x WHERE x.job_key=o.job_key ORDER BY observed_ts DESC,recorded_at DESC,observation_id DESC LIMIT 1)", unresolved_labels).fetchone()[0]
        invalid_catalog = conn.execute("SELECT count(*) FROM crawl_jobs WHERE kind LIKE '%catalog%' AND status='invalid'").fetchone()[0]
        now = _clock()
        scope = conn.execute("SELECT value FROM crawl_meta WHERE key='collection_scope'").fetchone()
        return {"collection_scope": scope[0] if scope else "legacy_with_chapters", "initialized": bool(conn.execute("SELECT 1 FROM crawl_meta WHERE key='initialized'").fetchone()), "counts": counts, "jobs": jobs,
                "distribution_plan": plan, "node_id": node, "owned_platforms": owned,
                "owned_jobs": [group for group in jobs if group["platform"] in owned],
                "works_by_platform": [dict(r) for r in conn.execute("SELECT platform,count(*) AS count FROM crawl_works GROUP BY platform")],
                "unresolved_catalog": unresolved + invalid_catalog,
                "blocked_jobs": conn.execute("SELECT count(*) FROM crawl_jobs WHERE status='blocked'").fetchone()[0],
                "platforms": [{**dict(r), "blocked": r["blocked_until"] > now} for r in conn.execute("SELECT * FROM crawl_platforms ORDER BY platform")]}

    def export(self, outdir):
        out = Path(outdir)
        out.mkdir(parents=True, exist_ok=True)
        database = out / "crawler.sqlite"
        if self.path == ":memory:" or database.resolve() != Path(self.path).resolve():
            staged = out / (".crawler-export-" + uuid.uuid4().hex + ".tmp")
            destination = sqlite3.connect(staged)
            try:
                self.conn.backup(destination)
                destination.close()
                os.replace(staged, database)
            finally:
                destination.close()
                staged.unlink(missing_ok=True)
        snapshot = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        snapshot.row_factory = sqlite3.Row
        try:
            snapshot.execute("BEGIN")
            for table, filename in (("crawl_works", "works_current.csv"), ("crawl_work_dates", "dates_current.csv")):
                cursor = snapshot.execute("SELECT * FROM " + table + " ORDER BY platform,work_id")
                with (out / filename).open("w", encoding="utf-8-sig", newline="") as stream:
                    writer = csv.writer(stream)
                    writer.writerow([c[0] for c in cursor.description])
                    writer.writerows(cursor)
            result = self.summary(_conn=snapshot)
        finally:
            snapshot.close()
        (out / "summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return result

    def close(self):
        self.conn.close()
