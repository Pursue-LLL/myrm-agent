"""SSOT snapshot for parallel live chrome E2E processes and flock holders."""

from __future__ import annotations

import json
import os
import re
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


def _extract_test_id(command: str) -> str | None:
    node_match = re.search(r"(tests/e2e/[^\s]+\.py(?:::([\w_]+))?)", command)
    if node_match is not None:
        path = node_match.group(1)
        if "::" in path:
            return path
        marker_match = re.search(r"-m\s+(\S+)", command)
        if marker_match is not None:
            return f"{path} -m {marker_match.group(1)}"
        return path
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
        rows.append(
            E2EActiveTest(
                pid=pid,
                test_id=test_id,
                elapsed_sec=_elapsed_to_seconds(elapsed),
                state=state,
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


def print_e2e_parallel_snapshot() -> E2EParallelSnapshot:
    snapshot = snapshot_live_e2e_processes()
    payload = {
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
    print(
        f"E2E_PARALLEL_SNAPSHOT_JSON={json.dumps(payload, ensure_ascii=False)}",
        flush=True,
    )
    if snapshot.active_tests:
        for row in snapshot.active_tests:
            print(
                "E2E_PARALLEL_ACTIVE: "
                f"pid={row.pid} state={row.state} elapsed={row.elapsed_sec:.0f}s "
                f"test={row.test_id}",
                flush=True,
            )
    else:
        print("E2E_PARALLEL_ACTIVE: none", flush=True)
    print(
        "E2E_PARALLEL_LOCKS: "
        f"agent_stream={format_lock_holder(snapshot.agent_stream_lock)} "
        f"desktop={format_lock_holder(snapshot.desktop_approval_lock)}",
        flush=True,
    )
    return snapshot
