"""SSOT snapshot for parallel live chrome E2E processes and flock holders."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path


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
    body_elapsed_sec: float | None = None
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


def _session_fields_for_pid(pid: int) -> tuple[str | None, str | None, float | None]:
    try:
        from tests.support.e2e_wall_progress import (  # noqa: PLC0415
            body_elapsed_sec_from_snapshot,
            read_e2e_session_snapshot,
        )
    except ImportError:
        return None, None, None
    snapshot = read_e2e_session_snapshot(pid)
    if snapshot is None:
        return None, None, None
    current_node = str(snapshot.get("currentNode") or "").strip() or None
    wall_phase = str(snapshot.get("phase") or "").strip().lower() or None
    body_elapsed = body_elapsed_sec_from_snapshot(snapshot)
    return current_node, wall_phase, body_elapsed


def _extract_test_id(command: str) -> str | None:
    marker = None
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = command.split()
    for idx, token in enumerate(argv):
        if token == "-m" and idx + 1 < len(argv):
            candidate = argv[idx + 1]
            if marker is None:
                marker = candidate
            if "chrome_e2e" in candidate:
                marker = candidate
                break
    marker_suffix = f" -m {marker}" if marker else ""

    node_match = re.search(r"(tests/e2e/[^\s]+\.py(?:::([\w_]+))?)", command)
    if node_match is not None:
        path = node_match.group(1)
        if "::" in path:
            return path
        if marker_suffix:
            return f"{path}{marker_suffix}"
        return path
    folder_match = re.search(r"tests/e2e/", command)
    if folder_match is not None:
        if marker_suffix:
            return f"tests/e2e/{marker_suffix}"
        return "tests/e2e/"
    if marker is not None and "chrome_e2e" in marker:
        return f"marker:{marker}"
    return None


def _list_active_pytest_chrome_e2e() -> tuple[E2EActiveTest, ...]:
    proc = subprocess.run(
        ["ps", "-eo", "pid=,stat=,etime=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ()
    rows: list[E2EActiveTest] = []
    seen_tests: set[str] = set()
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if not stripped or " -m pytest" not in stripped:
            continue
        if "tests/e2e/" not in stripped and "chrome_e2e" not in stripped:
            continue
        parts = stripped.split(maxsplit=3)
        if len(parts) < 4:
            continue
        pid_str, state, elapsed, command = parts
        test_id = _extract_test_id(command)
        if test_id is None or test_id in seen_tests:
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if not _pid_alive(pid):
            continue
        seen_tests.add(test_id)
        current_node, wall_phase, body_elapsed = _session_fields_for_pid(pid)
        rows.append(
            E2EActiveTest(
                pid=pid,
                test_id=test_id,
                elapsed_sec=_elapsed_to_seconds(elapsed),
                state=state,
                current_node=current_node,
                wall_phase=wall_phase,
                body_elapsed_sec=body_elapsed,
                batch_mode=_is_batch_file_invocation(test_id),
            )
        )
    return tuple(sorted(rows, key=lambda row: row.test_id))


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
        active_tests=_list_active_pytest_chrome_e2e(),
    )


def parallel_snapshot_to_dict(snapshot: E2EParallelSnapshot) -> dict[str, object]:
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
            if row.body_elapsed_sec is not None:
                detail += f" body_elapsed={row.body_elapsed_sec:.0f}s"
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
