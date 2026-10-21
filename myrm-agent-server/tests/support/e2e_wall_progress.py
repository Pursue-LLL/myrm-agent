"""Per-pid Chrome E2E wall progress — thin delegate to dev/lib SSOT (R62 Phase B)."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from e2e_session_runtime.lifecycle import ENV_PROGRESS_AT  # noqa: E402
from e2e_session_runtime.snapshot import (  # noqa: E402
    body_elapsed_from_snapshot,
    clear_session_snapshot,
    read_session_snapshot,
    read_session_snapshot_by_test_id,
    resolve_session_snapshot,
    touch_session_progress,
    write_session_snapshot,
)

_PROGRESS_BASENAME = "myrm-e2e-wall-progress.json"


def wall_progress_path() -> Path:
    return Path(os.environ.get("TMPDIR", "/tmp")) / _PROGRESS_BASENAME


def write_e2e_session_snapshot(*, current_node: str, phase: str | None = None) -> None:
    write_session_snapshot(current_node=current_node, phase=phase)


def touch_e2e_wall_progress(*, current_node: str | None = None) -> None:
    touch_session_progress(current_node=current_node)
    stamp = time.monotonic()
    path = wall_progress_path()
    path.write_text(json.dumps({"atMonotonic": stamp}), encoding="utf-8")


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


def resolve_e2e_session_snapshot(
    *,
    pid: int,
    test_id: str | None = None,
) -> dict[str, object] | None:
    return resolve_session_snapshot(pid=pid, test_id=test_id)


def read_e2e_session_snapshot_by_test_id(
    test_id: str,
) -> tuple[int, dict[str, object]] | None:
    return read_session_snapshot_by_test_id(test_id)


def read_e2e_session_snapshot(pid: int) -> dict[str, object] | None:
    return read_session_snapshot(pid)


def body_elapsed_sec_from_snapshot(snapshot: dict[str, object]) -> float | None:
    return body_elapsed_from_snapshot(snapshot)


def clear_e2e_session_snapshot(pid: int | None = None) -> None:
    clear_session_snapshot(pid)
