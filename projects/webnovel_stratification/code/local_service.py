"""Bounded local JJWXC collection under a macOS LaunchAgent.

prepare writes a reviewable plist; installation/bootstrap is a separate action.
Each tick launches the existing crawler once. Persistent pause markers keep
validation and internal failures from producing another unattended batch.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import subprocess
import sys
import time
import uuid

from cloud_state import validate_database
from crawl import check_output_file, write_json
from crawler_health import read_health
from crawler_store import Store


LABEL = "com.huwenbo.webnovel.local"
MAX_REQUESTS = 50
MAX_SECONDS = 300


class ServiceError(ValueError):
    pass


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def load_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ServiceError("expected_json_object")
    return value


def validate_local(db):
    validate_database(db)
    summary = Store.read_summary(db)
    if summary.get("node_id") != "local" or summary.get("owned_platforms") != ["jjwxc"]:
        raise ServiceError("service_requires_local_jjwxc_node")
    health = read_health(db, ["jjwxc"])
    if health["halt_required"]:
        raise ServiceError("invalid_jobs_require_repair:" + str(health["blocking_invalid_jobs"])
                           + ":" + ",".join(health["validation_circuits"]))
    summary.update(health)
    return summary


def load_config(directory):
    directory = Path(directory).resolve()
    config = load_json(directory / "config.json")
    if (config.get("schema_version") != 1 or config.get("node") != "local"
            or config.get("max_requests") != MAX_REQUESTS or config.get("max_seconds") != MAX_SECONDS
            or config.get("interval") not in (1800, 2100)
            or not isinstance(config.get("label"), str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", config["label"])
            or config.get("service_dir") != str(directory)):
        raise ServiceError("invalid_local_service_configuration")
    for key in ("db", "python", "script", "crawler"):
        if not isinstance(config.get(key), str) or not Path(config[key]).is_absolute():
            raise ServiceError("service_paths_must_be_absolute")
    if Path(config["script"]).resolve() != Path(__file__).resolve() or Path(config["crawler"]).resolve() != Path(__file__).with_name("crawl.py").resolve():
        raise ServiceError("unexpected_service_program")
    return config


@contextmanager
def service_lock(directory):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "service.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ServiceError("service_tick_already_running") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def prepare(db, directory, python=None, interval=2100, label=LABEL):
    db, directory = Path(db).resolve(), Path(directory).resolve()
    validate_local(db)
    if interval not in (1800, 2100) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", label):
        raise ServiceError("invalid_service_interval_or_label")
    # Preserve the final venv executable symlink: resolving it loses the venv.
    python = Path(python or sys.executable).absolute()
    if not python.is_file() or not os.access(python, os.X_OK):
        raise ServiceError("python_executable_missing")
    script = Path(__file__).resolve()
    config = {"schema_version": 1, "label": label, "node": "local", "db": str(db),
              "service_dir": str(directory), "python": str(python), "script": str(script),
              "crawler": str(script.with_name("crawl.py")), "interval": interval,
              "max_requests": MAX_REQUESTS, "max_seconds": MAX_SECONDS}
    directory.mkdir(parents=True, exist_ok=True)
    with service_lock(directory):
        config_path = directory / "config.json"
        if config_path.exists():
            existing = load_config(directory)
            if existing != config:
                raise ServiceError("existing_service_configuration_differs")
        for name in ("config.json", label + ".plist", "launchd.stdout.log", "launchd.stderr.log",
                     "collector.stdout.log", "collector.stderr.log", "service_status.json", "pause.json"):
            check_output_file(directory / name, [db])
        plist_path = directory / (label + ".plist")
        temporary = plist_path.with_suffix(".plist.tmp")
        check_output_file(temporary, [db])
        plist = {"Label": label, "ProgramArguments": [str(python), str(script), "tick", "--service-dir", str(directory)],
                 "WorkingDirectory": str(script.parents[1]), "RunAtLoad": True, "StartInterval": interval,
                 "ProcessType": "Background", "KeepAlive": False,
                 "EnvironmentVariables": {"PYTHONDONTWRITEBYTECODE": "1"},
                 "StandardOutPath": str(directory / "launchd.stdout.log"),
                 "StandardErrorPath": str(directory / "launchd.stderr.log")}
        write_json(config_path, config)
        temporary.write_bytes(plistlib.dumps(plist, fmt=plistlib.FMT_XML, sort_keys=True))
        temporary.replace(plist_path)
    return {"state": "prepared", "plist": str(plist_path), "config": config,
            "install_destination": str(Path.home() / "Library/LaunchAgents" / plist_path.name),
            "launchctl_target": f"gui/{os.getuid()}/{label}", "started": False}


def pause(directory, reason, detail=None):
    path = Path(directory) / "pause.json"
    # A concurrent operator stop takes precedence over the batch's final error.
    if path.exists():
        return load_json(path)
    marker = {"schema_version": 1, "paused_at": utc(), "reason": reason}
    if detail:
        marker["detail"] = detail
    temporary = path.parent / (".pause-" + uuid.uuid4().hex + ".json")
    try:
        write_json(temporary, marker)
        try:
            os.link(temporary, path)
        except FileExistsError:
            return load_json(path)
        return marker
    finally:
        temporary.unlink(missing_ok=True)


def receipt(directory, state, **details):
    value = {"schema_version": 1, "state": state, "updated_at": utc(), **details}
    write_json(Path(directory) / "service_status.json", value)
    return value


def tick(directory):
    directory = Path(directory).resolve()
    try:
        with service_lock(directory):
            marker = directory / "pause.json"
            if marker.exists():
                return receipt(directory, "paused", pause=load_json(marker), requested=False)
            try:
                config = load_config(directory)
                summary = validate_local(Path(config["db"]))
            except Exception as error:
                marker_data = pause(directory, "preflight_failed", type(error).__name__ + ":" + str(error))
                return receipt(directory, "paused", pause=marker_data, requested=False)
            state = next((row for row in summary["platforms"] if row["platform"] == "jjwxc"), {})
            if state.get("blocked_until", 0) > time.time():
                return receipt(directory, "cooldown", blocked_until=state["blocked_until"], requested=False)
            batches = directory / "batches"
            summary_path = batches / (uuid.uuid4().hex + ".summary.json")
            stdout, stderr = directory / "collector.stdout.log", directory / "collector.stderr.log"
            process, handlers, interrupted = None, {}, False
            def stop_child(_sig, _frame):
                nonlocal interrupted
                interrupted = True
                if process is not None and process.poll() is None:
                    process.send_signal(signal.SIGTERM)
            try:
                batches.mkdir(exist_ok=True)
                for path in (summary_path, stdout, stderr):
                    check_output_file(path, [Path(config["db"])])
                command = [config["python"], config["crawler"], "run", "--db", config["db"], "--node", "local",
                           "--platform", "auto", "--max-requests", str(MAX_REQUESTS), "--max-seconds", str(MAX_SECONDS),
                           "--summary", str(summary_path)]
                for sig in (signal.SIGINT, signal.SIGTERM):
                    handlers[sig] = signal.signal(sig, stop_child)
                if marker.exists():
                    return receipt(directory, "paused", pause=load_json(marker), requested=False)
                if interrupted:
                    return receipt(directory, "interrupted", requested=False)
                receipt(directory, "starting", wrapper_pid=os.getpid(), started_at=utc(), summary=str(summary_path))
                with stdout.open("a", encoding="utf-8") as output, stderr.open("a", encoding="utf-8") as errors:
                    process = subprocess.Popen(command, stdout=output, stderr=errors, cwd=str(Path(config["crawler"]).parents[1]))
                    receipt(directory, "running", wrapper_pid=os.getpid(), collector_pid=process.pid, summary=str(summary_path))
                    if interrupted:
                        process.send_signal(signal.SIGTERM)
                    try:
                        code = process.wait(timeout=MAX_SECONDS + 120)
                    except subprocess.TimeoutExpired:
                        process.terminate()
                        try:
                            process.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                        if interrupted and not marker.exists():
                            return receipt(directory, "interrupted", summary=str(summary_path))
                        pause(directory, "collector_timeout")
                        return receipt(directory, "paused", pause=load_json(marker), summary=str(summary_path))
                if marker.exists():
                    return receipt(directory, "paused", pause=load_json(marker), collector_exit=code, summary=str(summary_path))
                if interrupted:
                    # Login/logout and shutdown send signals too. Only an
                    # explicit operator stop writes a persistent pause marker.
                    return receipt(directory, "interrupted", collector_exit=code, summary=str(summary_path))
                if code != 0:
                    marker_data = pause(directory, "collector_exit_nonzero", str(code))
                    return receipt(directory, "paused", pause=marker_data, collector_exit=code, summary=str(summary_path))
                if not summary_path.is_file():
                    raise ServiceError("missing_summary")
                batch = load_json(summary_path)
                if (batch.get("node_id") != "local" or batch.get("owned_platforms") != ["jjwxc"]
                        or not isinstance(batch.get("workers"), list) or len(batch["workers"]) != 1
                        or not isinstance(batch["workers"][0], dict)
                        or batch["workers"][0].get("platform") != "jjwxc"
                        or not isinstance(batch.get("owned_jobs"), list)
                        or any(not isinstance(row, dict) or "status" not in row for row in batch["owned_jobs"])
                        or not isinstance(batch["workers"][0].get("errors", {}), dict)
                        or ("halt_required" in batch and not isinstance(batch["halt_required"], bool))):
                    raise ServiceError("invalid_summary")
                invalid = any(row["status"] == "invalid" for row in batch["owned_jobs"])
                errors = batch["workers"][0].get("errors", {})
                # New summaries distinguish isolated records from a validation
                # halt. Legacy summaries retain the conservative pause policy.
                halt_required = batch.get("halt_required", invalid or bool(errors.get("invalid")))
                health = read_health(Path(config["db"]), ["jjwxc"])
                if halt_required or health["halt_required"] or errors.get("internal"):
                    marker_data = pause(directory, "collector_internal_error" if errors.get("internal") else "invalid_jobs")
                    return receipt(directory, "paused", pause=marker_data, collector_exit=code, summary=str(summary_path))
                return receipt(directory, "ready", collector_exit=code, summary=str(summary_path),
                               needs_attention=bool(batch.get("needs_attention") or health["needs_attention"] or invalid or errors.get("invalid")),
                               quarantined_jobs=health["quarantined_jobs"],
                               halt_required=False,
                               last_exit_reason=batch["workers"][0].get("exit_reason"), completed_at=utc())
            except Exception as error:
                if interrupted and not marker.exists():
                    return receipt(directory, "interrupted", summary=str(summary_path))
                reason = str(error) if isinstance(error, ServiceError) and str(error) in {"missing_summary", "invalid_summary"} else "fatal_wrapper_error"
                marker_data = pause(directory, reason, type(error).__name__ + ":" + str(error))
                return receipt(directory, "paused", pause=marker_data, summary=str(summary_path))
            finally:
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=10)
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
    except ServiceError as error:
        if str(error) == "service_tick_already_running":
            return {"state": "already_running", "requested": False}
        raise


def launchctl(directory, *operation):
    config = load_config(directory)
    target = f"gui/{os.getuid()}/{config['label']}"
    result = subprocess.run(["/bin/launchctl", *operation, target], capture_output=True, text=True, timeout=10)
    return result


def status(directory, inspect_launchd=True):
    directory = Path(directory).resolve()
    config = load_config(directory)
    marker, state = directory / "pause.json", directory / "service_status.json"
    result = {"config": config, "paused": marker.exists(), "pause": load_json(marker) if marker.exists() else None,
              "last_receipt": load_json(state) if state.exists() else None}
    if inspect_launchd:
        try:
            check = launchctl(directory, "print")
            # Report only values observed from launchctl, never a saved PID as live.
            info = {"loaded": True if check.returncode == 0 else None, "checked_at": utc()}
            if check.returncode == 0:
                for field in ("state", "pid", "last exit code"):
                    match = re.search(r"^\s*" + re.escape(field) + r" = ([^\r\n]+)", check.stdout, re.M)
                    if match:
                        info[field.replace(" ", "_")] = int(match[1]) if field in {"pid", "last exit code"} and match[1].isdigit() else match[1].strip()
            else:
                if "Could not find service" in check.stderr:
                    info["loaded"] = False
                info["query_exit_code"] = check.returncode
            result["launchd"] = info
        except (OSError, subprocess.SubprocessError) as error:
            result["launchd"] = {"loaded": None, "query_error": type(error).__name__}
    return result


def stop(directory):
    directory = Path(directory).resolve()
    load_config(directory)
    marker = {"schema_version": 1, "paused_at": utc(), "reason": "operator_stop"}
    write_json(directory / "pause.json", marker)
    try:
        sent = launchctl(directory, "kill", "SIGTERM").returncode == 0
    except (OSError, subprocess.SubprocessError):
        sent = False
    return {"state": "paused", "pause": marker, "termination_signal_sent": sent,
            "note": "Future ticks stay paused; a running collector receives a graceful stop when launchd can reach it."}


def resume(directory, kickstart=True):
    directory = Path(directory).resolve()
    with service_lock(directory):
        config = load_config(directory)
        summary = validate_local(Path(config["db"]))
        marker = directory / "pause.json"
        if marker.exists():
            previous = load_json(marker)
            if previous.get("schema_version") != 1 or not isinstance(previous.get("reason"), str):
                raise ServiceError("invalid_pause_marker")
            marker.unlink()
        result = receipt(directory, "ready", resumed_at=utc(),
                         needs_attention=summary["needs_attention"],
                         quarantined_jobs=summary["quarantined_jobs"], halt_required=False)
    if kickstart:
        try:
            result["kickstart_requested"] = launchctl(directory, "kickstart").returncode == 0
        except (OSError, subprocess.SubprocessError):
            result["kickstart_requested"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preparation = commands.add_parser("prepare", help="Generate plist/config only; do not install or start")
    preparation.add_argument("--db", type=Path, required=True)
    preparation.add_argument("--service-dir", type=Path, required=True)
    preparation.add_argument("--python", type=Path, default=Path(sys.executable))
    preparation.add_argument("--interval", type=int, choices=[1800, 2100], default=2100)
    preparation.add_argument("--label", default=LABEL)
    for name in ("tick", "status", "stop", "resume"):
        command = commands.add_parser(name)
        command.add_argument("--service-dir", type=Path, required=True)
        if name == "resume":
            command.add_argument("--no-kickstart", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.db, args.service_dir, args.python, args.interval, args.label)
    elif args.command == "resume":
        result = resume(args.service_dir, kickstart=not args.no_kickstart)
    else:
        result = {"tick": tick, "status": status, "stop": stop}[args.command](args.service_dir)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
