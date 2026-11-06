#!/usr/bin/python
"""Download monitor helper for the com.mikezom.dlmon Plasma widget.

Producers write one JSON file per download job into the jobs directory
(protocol: README.md). The widget runs `dlmon.py status` and renders its output.

    dlmon.py status                 aggregated JSON for the widget (also prunes old finished jobs)
    dlmon.py report --id ID ...     create or update a job from a shell script
    dlmon.py remove --id ID         delete one job file
    dlmon.py clear                  delete finished, failed and stale jobs
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections.abc import Callable
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_STALE_AFTER_S = 300
FINISHED_RETENTION_S = 24 * 3600
ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
UNKNOWN_PERCENT = -1.0


class State(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    DONE = "done"
    FAILED = "failed"
    # Never written by producers: derived when a queued/running job stops sending heartbeats.
    STALE = "stale"


PRODUCER_STATES = {s.value for s in State if s is not State.STALE}
ACTIVE = {State.QUEUED, State.RUNNING}
FINISHED = {State.DONE, State.FAILED}
CLEARABLE = {State.DONE, State.FAILED, State.STALE}
SORT_ORDER = [State.RUNNING, State.QUEUED, State.STALE, State.FAILED, State.PAUSED, State.DONE]
STATE_LABELS = {
    State.QUEUED: "排队中",
    State.RUNNING: "下载中",
    State.PAUSED: "已暂停",
    State.DONE: "已完成",
    State.FAILED: "失败",
    State.STALE: "停滞",
}
INT_FIELDS = ("done_bytes", "total_bytes", "done_items", "total_items", "failed_items", "pid")
FLOAT_FIELDS = ("rate_bps", "eta_s", "started", "stale_after_s")
STR_FIELDS = ("message", "open")

PidAlive = Callable[[int], bool]


class InvalidJob(ValueError):
    pass


def default_jobs_dir() -> Path:
    state_home = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(state_home) / "dlmon" / "jobs"


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


# ---------------------------------------------------------------- protocol

def validate(job: dict[str, Any]) -> None:
    if job.get("v") != SCHEMA_VERSION:
        raise InvalidJob(f"v must be {SCHEMA_VERSION}")
    if not isinstance(job.get("id"), str) or not ID_PATTERN.fullmatch(job["id"]):
        raise InvalidJob("id must match [A-Za-z0-9._-]{1,128}")
    if not isinstance(job.get("title"), str) or not job["title"]:
        raise InvalidJob("title must be a non-empty string")
    if job.get("state") not in PRODUCER_STATES:
        raise InvalidJob(f"state must be one of {sorted(PRODUCER_STATES)}")
    if not isinstance(job.get("updated"), (int, float)):
        raise InvalidJob("updated must be unix seconds")
    for key in INT_FIELDS + FLOAT_FIELDS:
        value = job.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise InvalidJob(f"{key} must be a number or null")
    for key in STR_FIELDS:
        if job.get(key) is not None and not isinstance(job[key], str):
            raise InvalidJob(f"{key} must be a string or null")


def write_job(job: dict[str, Any], directory: Path, now: float | None = None) -> Path:
    """Reference writer: stamps `v` and `updated`, validates, then writes atomically."""
    record = {**job, "v": SCHEMA_VERSION, "updated": time.time() if now is None else now}
    validate(record)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record['id']}.json"
    tmp = directory / f".{record['id']}.json.tmp"
    tmp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


def load_jobs(directory: Path) -> tuple[list[dict[str, Any]], list[str]]:
    jobs: list[dict[str, Any]] = []
    errors: list[str] = []
    if not directory.is_dir():
        return jobs, errors
    for path in sorted(directory.glob("*.json")):
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(job, dict):
                raise InvalidJob("top level must be an object")
            validate(job)
            if job["id"] != path.stem:
                raise InvalidJob(f"id {job['id']!r} does not match file name")
        except (OSError, json.JSONDecodeError, InvalidJob) as e:
            errors.append(f"{path.name}: {e}")
            continue
        jobs.append(job)
    return jobs, errors


def effective_state(job: dict[str, Any], now: float, alive: PidAlive) -> tuple[State, str]:
    """Returns the state to show and, for STALE, why the heartbeat is considered lost."""
    state = State(job["state"])
    if state not in ACTIVE:
        return state, ""
    pid = job.get("pid")
    if pid is not None and not alive(int(pid)):
        return State.STALE, "进程已退出"
    silent_s = now - job["updated"]
    if silent_s > (job.get("stale_after_s") or DEFAULT_STALE_AFTER_S):
        return State.STALE, fmt_duration(silent_s) + "未更新"
    return state, ""


# ---------------------------------------------------------------- formatting

def fmt_bytes_pair(done: int | None, total: int | None) -> str:
    reference = total if total else done
    if reference is None:
        return ""
    for unit, scale, digits in (("GB", 1e9, 2), ("MB", 1e6, 1), ("KB", 1e3, 0)):
        if reference >= scale:
            break
    else:
        unit, scale, digits = "B", 1.0, 0

    def fmt(n: float) -> str:
        return f"{n / scale:.{digits}f}"

    if done is not None and total:
        return f"{fmt(done)} / {fmt(total)} {unit}"
    return f"{fmt(reference)} {unit}"


def fmt_rate(bps: float | None) -> str:
    if bps is None or bps <= 0:
        return ""
    if bps >= 1e6:
        return f"{bps / 1e6:.1f} MB/s"
    return f"{bps / 1e3:.0f} KB/s"


def fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return "不到 1 分钟"
    if s < 3600:
        return f"{s // 60} 分钟"
    if s < 48 * 3600:
        return f"{s // 3600} 小时 {s % 3600 // 60} 分"
    return f"{s // 86400} 天 {s % 86400 // 3600} 小时"


def fmt_clock(ts: float, now: float) -> str:
    t = time.localtime(ts)
    same_day = time.localtime(now)[:3] == t[:3]
    return time.strftime("%H:%M" if same_day else "%m-%d %H:%M", t)


# ---------------------------------------------------------------- aggregation

def job_percent(job: dict[str, Any]) -> float:
    if job.get("total_bytes") and job.get("done_bytes") is not None:
        ratio = job["done_bytes"] / job["total_bytes"]
    elif job.get("total_items") and job.get("done_items") is not None:
        ratio = job["done_items"] / job["total_items"]
    else:
        return UNKNOWN_PERCENT
    return max(0.0, min(100.0, ratio * 100))


def job_eta(job: dict[str, Any]) -> float | None:
    if job.get("eta_s") is not None:
        return float(job["eta_s"])
    rate, total, done = job.get("rate_bps"), job.get("total_bytes"), job.get("done_bytes")
    if rate and total and done is not None:
        return max(0.0, (total - done) / rate)
    return None


def job_detail(job: dict[str, Any], state: State, stale_note: str, now: float) -> str:
    parts = [fmt_bytes_pair(job.get("done_bytes"), job.get("total_bytes"))]
    if state in ACTIVE:
        parts.append(fmt_rate(job.get("rate_bps")))
        eta = job_eta(job)
        if eta is not None:
            parts.append("剩 " + fmt_duration(eta))
    elif state is State.STALE:
        parts.append(stale_note)
    else:
        parts.append(f"{STATE_LABELS[state]}于 {fmt_clock(job['updated'], now)}")
    return " · ".join(p for p in parts if p)


def job_items(job: dict[str, Any]) -> str:
    if not job.get("total_items"):
        return ""
    text = f"文件 {job.get('done_items') or 0}/{job['total_items']}"
    if job.get("failed_items"):
        text += f" · 失败 {job['failed_items']}"
    return text


def job_view(job: dict[str, Any], state: State, stale_note: str, now: float) -> dict[str, Any]:
    # Keys avoid `id`/`state`, which QML delegates reserve; every value is a string or number so a
    # ListModel keeps stable role types across refreshes.
    return {
        "jobId": job["id"],
        "title": job["title"],
        "jobState": state.value,
        "stateLabel": STATE_LABELS[state],
        "percent": job_percent(job),
        "detail": job_detail(job, state, stale_note, now),
        "itemsText": job_items(job),
        "message": job.get("message") or "",
        "openTarget": job.get("open") or "",
    }


def ring(active: list[dict[str, Any]], attention: int) -> dict[str, Any]:
    if active:
        if all(j.get("total_bytes") for j in active):
            done = sum(j.get("done_bytes") or 0 for j in active)
            value = done / sum(j["total_bytes"] for j in active) * 100
        else:
            known = [p for p in map(job_percent, active) if p != UNKNOWN_PERCENT]
            if not known:
                return {"mode": "indeterminate", "percent": UNKNOWN_PERCENT, "label": ""}
            value = sum(known) / len(known)
        value = max(0.0, min(100.0, value))
        return {"mode": "progress", "percent": value, "label": f"{value:.0f}%"}
    if attention:
        return {"mode": "attention", "percent": 100.0, "label": "!"}
    return {"mode": "idle", "percent": UNKNOWN_PERCENT, "label": ""}


def summarize(jobs: list[dict[str, Any]], errors: list[str], now: float, alive: PidAlive) -> dict[str, Any]:
    resolved = {j["id"]: effective_state(j, now, alive) for j in jobs}
    states = {k: v[0] for k, v in resolved.items()}
    ordered = sorted(jobs, key=lambda j: (SORT_ORDER.index(states[j["id"]]), -j["updated"]))
    active = [j for j in ordered if states[j["id"]] in ACTIVE]
    attention = sum(states[j["id"]] in (State.STALE, State.FAILED) for j in ordered)
    views = [job_view(j, *resolved[j["id"]], now) for j in ordered]
    r = ring(active, attention)
    rate = sum(j.get("rate_bps") or 0 for j in active)
    etas = [e for e in map(job_eta, active) if e is not None]

    main = "下载" + (f" · {r['label']}" if r["mode"] == "progress" else "")
    lines = []
    for view in views:
        if view["jobState"] != State.DONE.value:
            pct = f"{view['percent']:.0f}% · " if view["percent"] != UNKNOWN_PERCENT else ""
            lines.append(f"{view['title']}：{view['stateLabel']} · {pct}{view['detail']}".rstrip(" ·"))
    if errors:
        lines.append(f"{len(errors)} 个状态文件无法读取")
    return {
        "now": now,
        "active": len(active),
        "attention": attention,
        "ring": r,
        "rateText": fmt_rate(rate),
        "etaText": ("剩 " + fmt_duration(max(etas))) if etas else "",
        "tooltipMain": main,
        "tooltipSub": "\n".join(lines) or "没有进行中的下载",
        "jobs": views,
        "errors": errors,
    }


def prune(directory: Path, jobs: list[dict[str, Any]], now: float) -> list[dict[str, Any]]:
    kept = []
    for job in jobs:
        if State(job["state"]) in FINISHED and now - job["updated"] > FINISHED_RETENTION_S:
            (directory / f"{job['id']}.json").unlink(missing_ok=True)
        else:
            kept.append(job)
    return kept


def clear(directory: Path, now: float, alive: PidAlive) -> int:
    jobs, _ = load_jobs(directory)
    removed = 0
    for job in jobs:
        if effective_state(job, now, alive)[0] in CLEARABLE:
            (directory / f"{job['id']}.json").unlink(missing_ok=True)
            removed += 1
    return removed


def report(directory: Path, fields: dict[str, Any], now: float) -> Path:
    """Merge `fields` into the existing job (if any) so shell producers can send only what changed."""
    path = directory / f"{fields['id']}.json"
    base: dict[str, Any] = {}
    if path.exists():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # The file is this producer's own; a damaged one is replaced, and write_job rejects the
            # result if the fields given now are not enough to form a valid job.
            base = {}
    merged = {**base, **{k: v for k, v in fields.items() if v is not None}}
    merged.setdefault("started", now)
    return write_job(merged, directory, now)


# ---------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=None, help="jobs directory (default: $XDG_STATE_HOME/dlmon/jobs)")
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("status")
    sub.add_parser("clear")
    rm = sub.add_parser("remove")
    rm.add_argument("--id", required=True)
    rep = sub.add_parser("report")
    rep.add_argument("--id", required=True)
    rep.add_argument("--title")
    rep.add_argument("--state", choices=sorted(PRODUCER_STATES))
    for key in INT_FIELDS:
        rep.add_argument("--" + key.replace("_", "-"), dest=key, type=int)
    for key in FLOAT_FIELDS:
        rep.add_argument("--" + key.replace("_", "-"), dest=key, type=float)
    for key in STR_FIELDS:
        rep.add_argument("--" + key.replace("_", "-"), dest=key)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    directory: Path = args.dir or default_jobs_dir()
    now = time.time()
    if args.command == "status":
        jobs, errors = load_jobs(directory)
        jobs = prune(directory, jobs, now)
        print(json.dumps(summarize(jobs, errors, now, pid_alive), ensure_ascii=False))
    elif args.command == "clear":
        print(clear(directory, now, pid_alive))
    elif args.command == "remove":
        if not ID_PATTERN.fullmatch(args.id):
            print("invalid id", file=sys.stderr)
            return 2
        (directory / f"{args.id}.json").unlink(missing_ok=True)
    else:
        fields = {k: getattr(args, k) for k in ("id", "title", "state", *INT_FIELDS, *FLOAT_FIELDS, *STR_FIELDS)}
        try:
            print(report(directory, fields, now))
        except InvalidJob as e:
            print(f"invalid job: {e}", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
