"""Per-pid Chrome E2E wall progress + session snapshot (R39 / Agent e2e-context SSOT)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

ENV_PROGRESS_AT = "MYRM_E2E_WALL_PROGRESS_AT_MONOTONIC"
_PROGRESS_BASENAME = "myrm-e2e-wall-progress.json"
_SESSION_DIR_BASENAME = "myrm-e2e-session"


def wall_progress_path() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / _PROGRESS_BASENAME


def session_snapshot_dir() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / _SESSION_DIR_BASENAME


def session_snapshot_path(pid: int | None = None) -> Path:
    resolved = os.getpid() if pid is None else pid
    return session_snapshot_dir() / f"{resolved}.json"


def _read_phase_started_monotonic() -> float | None:
    raw = os.environ.get("MYRM_E2E_WALL_STARTED_MONOTONIC", "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _current_wall_phase() -> str:
    return os.environ.get("MYRM_E2E_WALL_PHASE", "admit").strip().lower() or "admit"


def write_e2e_session_snapshot(*, current_node: str, phase: str | None = None) -> None:
    """Persist per-pytest session state for ./myrm e2e-context (parallel-safe)."""
    now = time.monotonic()
    resolved_phase = (phase or _current_wall_phase()).strip().lower() or "body"
    started = _read_phase_started_monotonic() or now
    payload = {
        "pid": os.getpid(),
        "currentNode": current_node,
        "phase": resolved_phase,
        "bodyStartedMonotonic": started,
        "progressAtMonotonic": now,
        "updatedAtEpoch": time.time(),
    }
    session_snapshot_dir().mkdir(parents=True, exist_ok=True)
    session_snapshot_path().write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )


def touch_e2e_wall_progress(*, current_node: str | None = None) -> None:
    stamp = time.monotonic()
    os.environ[ENV_PROGRESS_AT] = str(stamp)
    path = wall_progress_path()
    path.write_text(json.dumps({"atMonotonic": stamp}), encoding="utf-8")
    node = current_node
    if node is None:
        raw = os.environ.get("PYTEST_CURRENT_TEST", "").strip()
        node = raw.split(" ", 1)[0] if raw else ""
    if node:
        write_e2e_session_snapshot(current_node=node)


def read_wall_progress_monotonic() -> float | None:
    env_raw = os.environ.get(ENV_PROGRESS_AT, "").strip()
    if env_raw:
        try:
            return float(env_raw)
        except ValueError:
            pass
    path = wall_progress_path()
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = payload.get("atMonotonic")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def read_e2e_session_snapshot(pid: int) -> dict[str, object] | None:
    path = session_snapshot_path(pid)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def body_elapsed_sec_from_snapshot(snapshot: dict[str, object]) -> float | None:
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase != "body":
        return None
    started = snapshot.get("bodyStartedMonotonic")
    if started is None:
        return None
    try:
        started_f = float(started)
    except (TypeError, ValueError):
        return None
    return max(0.0, time.monotonic() - started_f)


def clear_e2e_session_snapshot(pid: int | None = None) -> None:
    path = session_snapshot_path(pid)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
