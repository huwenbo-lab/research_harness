"""Restore and publish the crawler's durable GitHub Release state.

Normal collection must restore an existing, audited state. The separate bootstrap
command is explicit: a missing pointer never initializes a normal scheduled run.
All snapshot assets are immutable; only latest.json is replaced, last of all.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


POINTER_TAG = "webnovel-crawler-state"
POINTER_ASSET = "latest.json"
REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*")
SNAPSHOT_PATTERN = re.compile(r"crawler-([1-9][0-9]*)-([1-9][0-9]*)(?:-b([1-9][0-9]*))?\.sqlite\.gz")
REQUIRED_TABLES = (
    "work_master", "crawl_meta", "crawl_jobs", "crawl_platforms", "crawl_events",
    "crawl_observations", "crawl_works", "crawl_work_dates", "crawl_date_evidence",
    "crawl_chapters", "crawl_pages", "crawl_conflicts",
)


class StateError(RuntimeError):
    """The current state cannot safely be restored or advanced."""


def validate_repository(repo: str) -> str:
    if not isinstance(repo, str) or not REPOSITORY_PATTERN.fullmatch(repo):
        raise StateError("Repository must be OWNER/REPO, with no URL or path components")
    if any(part in {".", ".."} or part.endswith(".git") for part in repo.split("/")):
        raise StateError("Invalid repository name")
    return repo


def validate_pointer(pointer: object, repo: str) -> dict:
    """Accept only same-repository, named monthly snapshots; never arbitrary URLs."""
    validate_repository(repo)
    if not isinstance(pointer, dict):
        raise StateError("State pointer must be an object")
    required = {"schema_version", "source_repo", "tag", "asset", "run_id", "attempt"}
    if not required.issubset(pointer) or set(pointer) - required - {"published_at", "batch"}:
        raise StateError("State pointer has missing or unsupported fields")
    if type(pointer["schema_version"]) is not int or pointer["schema_version"] != 1:
        raise StateError("Unsupported state pointer schema")
    if pointer["source_repo"] != repo:
        raise StateError("State pointer belongs to another repository")
    tag = pointer["tag"]
    if not isinstance(tag, str) or not re.fullmatch(r"webnovel-crawler-[0-9]{6}", tag):
        raise StateError("Invalid monthly snapshot tag")
    try:
        datetime.strptime(tag.removeprefix("webnovel-crawler-"), "%Y%m")
    except ValueError as exc:
        raise StateError("Invalid snapshot month") from exc
    asset = pointer["asset"]
    match = SNAPSHOT_PATTERN.fullmatch(asset) if isinstance(asset, str) else None
    if not match:
        raise StateError("Invalid snapshot asset name")
    if not isinstance(pointer["run_id"], str) or pointer["run_id"] != match[1]:
        raise StateError("Snapshot run ID does not match its asset")
    if type(pointer["attempt"]) is not int or str(pointer["attempt"]) != match[2]:
        raise StateError("Snapshot attempt does not match its asset")
    if "batch" in pointer:
        if type(pointer["batch"]) is not int or pointer["batch"] < 1 or str(pointer["batch"]) != match[3]:
            raise StateError("Snapshot batch does not match its asset")
    elif match[3] is not None:
        raise StateError("Snapshot asset requires its batch field")
    if "published_at" in pointer:
        value = pointer["published_at"]
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if stamp.utcoffset() is None:
                raise ValueError("missing time zone")
        except (AttributeError, TypeError, ValueError) as exc:
            raise StateError("Invalid publication timestamp") from exc
    return pointer


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateError(f"Cannot read JSON: {path.name}") from exc
    if not isinstance(value, dict):
        raise StateError(f"Expected a JSON object: {path.name}")
    return value


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_database(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise StateError("A nonempty existing database is required")
    try:
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            integrity = db.execute("PRAGMA integrity_check").fetchall()
            if integrity != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchone():
                raise StateError("Database integrity or foreign-key check failed")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not set(REQUIRED_TABLES).issubset(tables):
                raise StateError("Database is missing required research or checkpoint tables")
            initialized = db.execute("SELECT value FROM crawl_meta WHERE key='initialized'").fetchone()
            if not initialized or not initialized[0]:
                raise StateError("Database has not completed explicit initialization")
            if not db.execute("SELECT 1 FROM crawl_works LIMIT 1").fetchone():
                raise StateError("Refusing an empty research database")
            if not db.execute("SELECT 1 FROM crawl_jobs LIMIT 1").fetchone():
                raise StateError("Refusing a database without its persistent task queue")
    except sqlite3.Error as exc:
        raise StateError("Cannot read a valid SQLite research database") from exc


class GitHubReleases:
    def __init__(self, repo: str, runner=None, sleeper=None):
        self.repo = validate_repository(repo)
        self.runner = runner or subprocess.run
        self.sleeper = sleeper or time.sleep

    def command(self, *args: str, retry_read=False) -> str:
        attempts = 3 if retry_read else 1
        for attempt in range(attempts):
            try:
                options = {"capture_output": True, "text": True}
                if retry_read:
                    options["timeout"] = 120
                result = self.runner(["gh", *args], **options)
                if result.returncode == 0:
                    return result.stdout
                error = str(result.stderr or "").lower()
                permanent = bool(re.search(r"http (?:401|403|404)|authorization failed|authentication failed|bad credentials|not logged|not found|no assets match|permission denied", error))
                retryable = not permanent or "rate limit" in error
                reason = f"exit {result.returncode}"
            except subprocess.TimeoutExpired:
                retryable, reason = True, "timeout"
            if not retry_read or not retryable or attempt == attempts - 1:
                # Do not print remote bodies or credentials from gh stderr.
                raise StateError(f"GitHub command failed ({' '.join(args[:2])}, {reason}, attempts {attempt + 1})")
            self.sleeper((5, 15)[attempt])
        raise AssertionError("unreachable")

    def download(self, tag: str, asset: str, directory: Path) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", asset) or ".." in asset:
            raise StateError("Asset must be a single filename")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / asset
        if path.exists() or path.is_symlink():
            raise StateError("Download destination already exists")
        # Retry into a private staging directory: gh may leave a partial file.
        # --clobber applies only to that staging file, never retained data.
        with tempfile.TemporaryDirectory(prefix=".download-", dir=directory) as tmp:
            self.command("release", "download", tag, "--repo", self.repo,
                         "--pattern", asset, "--dir", tmp, "--clobber", retry_read=True)
            staged = Path(tmp) / asset
            if not staged.is_file() or staged.is_symlink():
                raise StateError("GitHub did not return the requested asset")
            os.link(staged, path)  # Exclusive publication; cannot overwrite a destination.
        return path

    def ensure_monthly_release(self, tag: str, target: str) -> None:
        # A network/authentication error must not be mistaken for a missing release.
        tags = self.command("api", "--paginate", f"repos/{self.repo}/releases",
                            "--jq", ".[].tag_name", retry_read=True).splitlines()
        if tag not in tags:
            self.command("release", "create", tag, "--repo", self.repo,
                         "--target", target, "--latest=false", "--title", tag,
                         "--notes", "Immutable audited crawler snapshots; latest.json is stored in webnovel-crawler-state.")

    def ensure_pointer_release(self, target: str) -> None:
        self.ensure_monthly_release(POINTER_TAG, target)

    def inventory(self) -> dict[str, set[str]]:
        """Read every relevant release and asset page; errors never mean absence."""
        def pages(endpoint):
            try:
                value = json.loads(self.command("api", "--paginate", "--slurp", endpoint, retry_read=True))
            except ValueError as exc:
                raise StateError("GitHub inventory returned invalid JSON") from exc
            if not isinstance(value, list) or not all(isinstance(page, list) for page in value):
                raise StateError("GitHub inventory returned an invalid page structure")
            return [item for page in value for item in page]

        releases = pages(f"repos/{self.repo}/releases")
        result = {}
        for release in releases:
            if not isinstance(release, dict) or not isinstance(release.get("tag_name"), str):
                raise StateError("GitHub inventory returned an invalid release")
            tag = release["tag_name"]
            if tag != POINTER_TAG and not re.fullmatch(r"webnovel-crawler-[0-9]{6}", tag):
                continue
            if type(release.get("id")) is not int or release["id"] <= 0 or tag in result:
                raise StateError("GitHub inventory returned an invalid release identity")
            assets = pages(f"repos/{self.repo}/releases/{release['id']}/assets")
            if not all(isinstance(asset, dict) and isinstance(asset.get("name"), str) for asset in assets):
                raise StateError("GitHub inventory returned invalid assets")
            result[tag] = {asset["name"] for asset in assets}
        return result

    def upload(self, tag: str, path: Path, *, replace: bool = False) -> None:
        args = ["release", "upload", tag, str(path), "--repo", self.repo]
        if replace:
            args.append("--clobber")
        self.command(*args)


def fetch_pointer(store: GitHubReleases, repo: str) -> dict:
    with tempfile.TemporaryDirectory(prefix="webnovel-pointer-") as tmp:
        path = store.download(POINTER_TAG, POINTER_ASSET, Path(tmp))
        return validate_pointer(read_json(path), repo)


def restore(store: GitHubReleases, repo: str, out: Path, receipt: Path) -> dict:
    if out.exists() or receipt.exists():
        raise StateError("Restore destinations must be new; existing state is never overwritten")
    if out.resolve() == receipt.resolve():
        raise StateError("Database and restore receipt must have different paths")
    pointer = fetch_pointer(store, repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    # Build the complete file beside its destination, then rename it atomically.
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=out.parent) as tmp:
        directory = Path(tmp)
        compressed = store.download(pointer["tag"], pointer["asset"], directory)
        candidate = directory / "crawler.sqlite"
        try:
            with gzip.open(compressed, "rb") as source, candidate.open("wb") as target:
                shutil.copyfileobj(source, target)
        except (OSError, EOFError) as exc:
            raise StateError("Could not decompress the previous state; collection must stop") from exc
        validate_database(candidate)
        candidate.replace(out)
    record = {"schema_version": 1, "source_repo": repo, "pointer": pointer,
              "database": str(out.resolve())}
    write_json(receipt, record)
    return record


def require_uninitialized(store: GitHubReleases, own_assets: dict[str, set[str]] | None = None) -> None:
    """Do not mistake a missing/deleted pointer for a fresh state repository."""
    permitted = own_assets or {}
    for tag, assets in store.inventory().items():
        if assets - permitted.get(tag, set()):
            raise StateError("Cloud state or prior snapshot assets already exist; bootstrap refuses replacement")


def _publish_snapshot(store: GitHubReleases, repo: str, db: Path, summary: Path,
                      audit: Path, run_id: str, attempt: int, target: str,
                      now: datetime | None, previous_pointer: dict | None,
                      batch: int | None = None) -> dict:
    validate_repository(repo)
    if not re.fullmatch(r"[1-9][0-9]*", run_id) or type(attempt) is not int or attempt < 1:
        raise StateError("Run ID and attempt must be positive GitHub run identifiers")
    if batch is not None and (type(batch) is not int or batch < 1):
        raise StateError("Batch must be a positive integer")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", target) or ".." in target:
        raise StateError("Invalid release target")
    audit_data = read_json(audit)
    if audit_data.get("passed") is not True:
        raise StateError("Only a passing audit may advance the state pointer")
    if not isinstance(audit_data.get("database"), str) or Path(audit_data["database"]).resolve() != db.resolve():
        raise StateError("Audit does not describe the database being published")
    if not isinstance(audit_data.get("previous"), str) or not audit_data["previous"]:
        raise StateError("Audit must compare the snapshot with its restored predecessor")
    read_json(summary)
    validate_database(db)
    if previous_pointer is None:
        require_uninitialized(store)
    elif fetch_pointer(store, repo) != previous_pointer:
        raise StateError("State pointer changed after restore; refusing to overwrite newer state")
    stamp = now or datetime.now(timezone.utc)
    if stamp.utcoffset() is None:
        raise StateError("Publication time requires a time zone")
    stamp = stamp.astimezone(timezone.utc)
    tag = "webnovel-crawler-" + stamp.strftime("%Y%m")
    stem = f"crawler-{run_id}-{attempt}"
    if batch is not None:
        stem += f"-b{batch}"
    pointer = {"schema_version": 1, "source_repo": repo, "tag": tag,
               "asset": stem + ".sqlite.gz", "run_id": run_id, "attempt": attempt,
               "published_at": stamp.isoformat()}
    if batch is not None:
        pointer["batch"] = batch
    validate_pointer(pointer, repo)
    with tempfile.TemporaryDirectory(prefix="webnovel-publish-") as tmp:
        directory = Path(tmp)
        compressed = directory / pointer["asset"]
        # export supplies a closed, standalone SQLite backup (no WAL sidecar).
        if Path(str(db) + "-wal").exists() and Path(str(db) + "-wal").stat().st_size:
            raise StateError("Publish a standalone exported database, not an active WAL database")
        with db.open("rb") as source, gzip.open(compressed, "wb", compresslevel=6) as dest:
            shutil.copyfileobj(source, dest)
        summary_asset = directory / (stem + ".summary.json")
        audit_asset = directory / (stem + ".audit.json")
        shutil.copyfile(summary, summary_asset)
        shutil.copyfile(audit, audit_asset)
        pointer_asset = directory / POINTER_ASSET
        write_json(pointer_asset, pointer)
        store.ensure_monthly_release(tag, target)
        # Failed uploads leave the old pointer intact. Snapshot uploads never use
        # --clobber; reruns receive GitHub's new run_attempt and new asset names.
        for asset in (compressed, summary_asset, audit_asset):
            store.upload(tag, asset)
        if previous_pointer is None:
            own = {tag: {compressed.name, summary_asset.name, audit_asset.name}}
            require_uninitialized(store, own_assets=own)
            store.ensure_pointer_release(target)
            # Initial publication never clobbers. If another bootstrap raced us,
            # GitHub rejects an existing latest.json rather than replacing it.
            store.upload(POINTER_TAG, pointer_asset)
        else:
            if fetch_pointer(store, repo) != previous_pointer:
                raise StateError("State pointer changed during upload; uploaded snapshot remains unreferenced")
            # GitHub replaces release assets by delete/create. If interrupted here,
            # restore fails closed until the pointer is repaired from retained assets.
            store.upload(POINTER_TAG, pointer_asset, replace=True)
    if fetch_pointer(store, repo) != pointer:
        raise StateError("Published pointer could not be verified; inspect retained release assets")
    return pointer


def publish(store: GitHubReleases, repo: str, db: Path, summary: Path, audit: Path,
            restored: Path, run_id: str, attempt: int, target: str,
            now: datetime | None = None, batch: int | None = None) -> dict:
    validate_repository(repo)
    record = read_json(restored)
    if record.get("schema_version") != 1 or record.get("source_repo") != repo:
        raise StateError("Restore receipt does not belong to this repository")
    previous_pointer = validate_pointer(record.get("pointer"), repo)
    return _publish_snapshot(store, repo, db, summary, audit, run_id, attempt,
                             target, now, previous_pointer, batch=batch)


def bootstrap(store: GitHubReleases, repo: str, db: Path, summary: Path, audit: Path,
              run_id: str, attempt: int, target: str,
              now: datetime | None = None) -> dict:
    """Explicit first publication only; existing or unreadable cloud state stops it."""
    return _publish_snapshot(store, repo, db, summary, audit, run_id, attempt,
                             target, now, previous_pointer=None)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    restore_parser = commands.add_parser("restore", help="Restore an existing pointer and snapshot; never initialize")
    restore_parser.add_argument("--repo", required=True)
    restore_parser.add_argument("--out", type=Path, required=True)
    restore_parser.add_argument("--receipt", type=Path, required=True)
    publish_parser = commands.add_parser("publish", help="Upload an audited immutable snapshot, then advance latest.json")
    bootstrap_parser = commands.add_parser("bootstrap", help="Explicit first upload; refuse any existing cloud state or snapshot assets")
    for command in (publish_parser, bootstrap_parser):
        command.add_argument("--repo", required=True)
        command.add_argument("--db", type=Path, required=True)
        command.add_argument("--summary", type=Path, required=True)
        command.add_argument("--audit", type=Path, required=True)
        command.add_argument("--run-id", required=True)
        command.add_argument("--attempt", type=int, required=True)
        command.add_argument("--target", required=True, help="The checked-out commit for a new release tag")
    publish_parser.add_argument("--restored", type=Path, required=True)
    publish_parser.add_argument("--batch", type=int, help="Positive batch number within the unchanged GitHub run and attempt")
    args = parser.parse_args()
    try:
        store = GitHubReleases(args.repo)
        if args.command == "restore":
            value = restore(store, args.repo, args.out, args.receipt)
        elif args.command == "bootstrap":
            value = bootstrap(store, args.repo, args.db, args.summary, args.audit,
                              args.run_id, args.attempt, args.target)
        else:
            value = publish(store, args.repo, args.db, args.summary, args.audit,
                            args.restored, args.run_id, args.attempt, args.target, batch=args.batch)
        print(json.dumps(value, ensure_ascii=False))
        return 0
    except (StateError, OSError) as exc:
        parser.exit(1, f"cloud state stopped: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
