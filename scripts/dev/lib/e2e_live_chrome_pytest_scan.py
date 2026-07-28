"""SSOT scan for live chrome_e2e pytest processes (wrapper dedupe + snapshot pid).

[INPUT]
- ps(1) process list
- e2e_session_snapshot per-pid / per-test_id sidecars

[OUTPUT]
- list_live_chrome_e2e_pytest_rows(): canonical one row per test_id (inner pytest preferred)

[POS]
Dev Gate layer — shared by e2e-context, hung reap, and lease hygiene.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
from dataclasses import dataclass, replace

from e2e_session_snapshot import (
    read_session_snapshot,
    read_session_snapshot_by_test_id,
    test_ids_match,
)


@dataclass(frozen=True, slots=True)
class LiveChromeE2ERow:
    pid: int
    elapsed_sec: float
    command: str
    test_id: str
    state: str = "?"
    is_wrapper: bool = False


def is_run_pytest_safe_wrapper(command: str) -> bool:
    return "run_pytest_safe" in command


def _elapsed_to_seconds(raw: str) -> float:
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


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def extract_chrome_e2e_test_id(command: str) -> str | None:
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


def _pick_canonical_row(group: tuple[LiveChromeE2ERow, ...]) -> LiveChromeE2ERow:
    if len(group) == 1:
        row = group[0]
    else:
        for row in group:
            if read_session_snapshot(row.pid) is not None:
                return row
        inner = tuple(r for r in group if not r.is_wrapper)
        row = max(inner, key=lambda item: item.pid) if inner else group[0]

    match = read_session_snapshot_by_test_id(row.test_id)
    if match is None:
        return row
    snap_pid, _payload = match
    if row.pid == snap_pid:
        return row
    if _pid_alive(snap_pid):
        return replace(row, pid=snap_pid, is_wrapper=False)
    return row


def list_live_chrome_e2e_pytest_rows() -> tuple[LiveChromeE2ERow, ...]:
    proc = subprocess.run(
        ["ps", "-eo", "pid=,stat=,etime=,command="],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return ()
    grouped: dict[str, list[LiveChromeE2ERow]] = {}
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
        test_id = extract_chrome_e2e_test_id(command)
        if test_id is None:
            continue
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if not _pid_alive(pid):
            continue
        row = LiveChromeE2ERow(
            pid=pid,
            elapsed_sec=_elapsed_to_seconds(elapsed),
            command=command,
            test_id=test_id,
            state=state,
            is_wrapper=is_run_pytest_safe_wrapper(command),
        )
        grouped.setdefault(test_id, []).append(row)

    canonical: list[LiveChromeE2ERow] = []
    for test_id in sorted(grouped):
        canonical.append(_pick_canonical_row(tuple(grouped[test_id])))
    return tuple(canonical)


def rows_share_test_id(left: str, right: str) -> bool:
    return test_ids_match(left, right)
