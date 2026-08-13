"""SSOT snapshot for parallel live chrome E2E processes and flock holders."""

from __future__ import annotations

import json
import os
import sys
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from e2e_session_runtime.registry import (  # noqa: E402
    LiveE2ESessionRow,
    admit_active_count,
    body_active_count,
    list_live_e2e_sessions,
)
from e2e_session_runtime.snapshot import (  # noqa: E402
    body_elapsed_from_snapshot,
    resolve_session_snapshot,
)
from e2e_core.stall_guard import node_elapsed_from_snapshot  # noqa: E402


@dataclass(frozen=True, slots=True)
class E2ELockHolder:
    pid: int
    label: str


@dataclass(frozen=True, slots=True)
class E2EActiveTest:
    pid: int
    test_id: str
    elapsed_sec: float
    state: str
    current_node: str | None = None
    wall_phase: str | None = None
    admit_elapsed_sec: float | None = None
    body_elapsed_sec: float | None = None
    node_elapsed_sec: float | None = None
    batch_mode: bool = False


@dataclass(frozen=True, slots=True)
class E2EParallelSnapshot:
    agent_stream_lock: E2ELockHolder | None
    desktop_approval_lock: E2ELockHolder | None
    active_tests: tuple[E2EActiveTest, ...]


def lock_holder_path(lock_path: Path) -> Path:
    return lock_path.parent / f"{lock_path.name}.holder"


def current_pytest_node_label(fallback: str = "pytest") -> str:
    raw = os.environ.get("PYTEST_CURRENT_TEST", "").strip()
    if raw:
        return raw.split(" ", 1)[0]
    return fallback


def write_e2e_lock_holder(lock_path: Path, label: str) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_holder_path(lock_path).write_text(f"{os.getpid()}:{label}\n", encoding="utf-8")


def clear_e2e_lock_holder(lock_path: Path) -> None:
    with suppress(OSError):
        lock_holder_path(lock_path).unlink()


def read_e2e_lock_holder(lock_path: Path) -> E2ELockHolder | None:
    holder_file = lock_holder_path(lock_path)
    if not holder_file.is_file():
        return None
    raw = holder_file.read_text(encoding="utf-8").strip()
    if ":" not in raw:
        return None
    pid_str, label = raw.split(":", 1)
    try:
        pid = int(pid_str)
    except ValueError:
        return None
    if not _pid_alive(pid):
        clear_e2e_lock_holder(lock_path)
        return None
    return E2ELockHolder(pid=pid, label=label.strip() or "unknown")


def format_lock_holder(holder: E2ELockHolder | None) -> str:
    if holder is None:
        return "none"
    return f"pid={holder.pid} test={holder.label}"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _elapsed_to_seconds(raw: str) -> float:
    """Parse `ps etime` ([[dd-]hh:]mm:ss) into seconds."""
    text = raw.strip()
    if not text:
        return 0.0
    if text.isdigit():
        return float(text)
    days = 0
    if "-" in text:
        day_part, text = text.split("-", 1)
        try:
            days = int(day_part)
        except ValueError:
            return 0.0
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return float(days * 86_400 + int(parts[0]))
        if len(parts) == 2:
            minutes, seconds = int(parts[0]), int(parts[1])
            return float(days * 86_400 + minutes * 60 + seconds)
        if len(parts) == 3:
            hours, minutes, seconds = int(parts[0]), int(parts[1]), int(parts[2])
            return float(days * 86_400 + hours * 3_600 + minutes * 60 + seconds)
    except ValueError:
        return 0.0
    return 0.0


def _is_batch_file_invocation(test_id: str) -> bool:
    if "::" in test_id:
        return False
    return " -m " in test_id and "chrome_e2e" in test_id


def _session_fields_for_pid(
    pid: int,
    *,
    test_id: str | None = None,
) -> tuple[str | None, str | None, float | None, float | None]:
    snapshot = resolve_session_snapshot(pid=pid, test_id=test_id)
    if snapshot is None:
        return None, None, None, None
    current_node = str(snapshot.get("currentNode") or "").strip() or None
    wall_phase = str(snapshot.get("phase") or "").strip().lower() or None
    body_elapsed = body_elapsed_from_snapshot(snapshot)
    node_elapsed = node_elapsed_from_snapshot(snapshot)
    return current_node, wall_phase, body_elapsed, node_elapsed


def _session_row_to_active_test(row: LiveE2ESessionRow) -> E2EActiveTest:
    return E2EActiveTest(
        pid=row.pid,
        test_id=row.test_id,
        elapsed_sec=row.elapsed_sec,
        state=row.state,
        current_node=row.current_node,
        wall_phase=row.wall_phase,
        admit_elapsed_sec=row.admit_elapsed_sec,
        body_elapsed_sec=row.body_elapsed_sec,
        node_elapsed_sec=row.node_elapsed_sec,
        batch_mode=row.batch_mode,
    )


def _list_active_e2e_sessions() -> tuple[E2EActiveTest, ...]:
    rows: list[E2EActiveTest] = []
    for row in list_live_e2e_sessions():
        active = _session_row_to_active_test(row)
        rows.append(active)
    return tuple(rows)


def snapshot_live_e2e_processes(
    *,
    agent_stream_lock_path: Path | None = None,
    desktop_approval_lock_path: Path | None = None,
) -> E2EParallelSnapshot:
    tmp = Path(os.environ.get("TMPDIR", "/tmp"))
    stream_path = agent_stream_lock_path or (tmp / "myrm-live-agent-stream.lock")
    desktop_path = desktop_approval_lock_path or (
        tmp / "myrm-desktop-approval-e2e.lock"
    )
    return E2EParallelSnapshot(
        agent_stream_lock=read_e2e_lock_holder(stream_path),
        desktop_approval_lock=read_e2e_lock_holder(desktop_path),
        active_tests=_list_active_e2e_sessions(),
    )


def parallel_snapshot_to_dict(snapshot: E2EParallelSnapshot) -> dict[str, object]:
    sessions = list_live_e2e_sessions()
    return {
        "agent_stream_lock": (
            asdict(snapshot.agent_stream_lock) if snapshot.agent_stream_lock else None
        ),
        "desktop_approval_lock": (
            asdict(snapshot.desktop_approval_lock)
            if snapshot.desktop_approval_lock
            else None
        ),
        "active_tests": [asdict(row) for row in snapshot.active_tests],
        "active_test_count": len(snapshot.active_tests),
        "admit_active_count": admit_active_count(sessions),
        "body_active_count": body_active_count(sessions),
    }


def format_parallel_snapshot_human(snapshot: E2EParallelSnapshot) -> list[str]:
    lines: list[str] = []
    if snapshot.active_tests:
        for row in snapshot.active_tests:
            detail = (
                "E2E_PARALLEL_ACTIVE: "
                f"pid={row.pid} state={row.state} process_elapsed={row.elapsed_sec:.0f}s "
                f"test={row.test_id}"
            )
            if row.current_node:
                detail += f" current_node={row.current_node}"
            if row.wall_phase:
                detail += f" wall_phase={row.wall_phase}"
            if row.admit_elapsed_sec is not None:
                detail += f" admit_elapsed={row.admit_elapsed_sec:.0f}s"
            if row.body_elapsed_sec is not None:
                detail += f" body_elapsed={row.body_elapsed_sec:.0f}s"
            if row.node_elapsed_sec is not None:
                detail += f" node_elapsed={row.node_elapsed_sec:.0f}s"
            if row.batch_mode:
                detail += " batch_mode=yes"
            lines.append(detail)
    else:
        lines.append("E2E_PARALLEL_ACTIVE: none")
    lines.append(
        "E2E_PARALLEL_LOCKS: "
        f"agent_stream={format_lock_holder(snapshot.agent_stream_lock)} "
        f"desktop={format_lock_holder(snapshot.desktop_approval_lock)}"
    )
    return lines


def print_e2e_parallel_snapshot() -> E2EParallelSnapshot:
    snapshot = snapshot_live_e2e_processes()
    payload = parallel_snapshot_to_dict(snapshot)
    print(
        f"E2E_PARALLEL_SNAPSHOT_JSON={json.dumps(payload, ensure_ascii=False)}",
        flush=True,
    )
    for line in format_parallel_snapshot_human(snapshot):
        print(line, flush=True)
    return snapshot
