"""Unified E2E session registry — ADMIT through BODY (R144 SSOT).

[INPUT]
- e2e_session_runtime.snapshot sidecars
- dev_gate_cli (POS: Unix socket 协调器自动启动客户端) — coordinator 活跃性检测
- ps(1) etime for live holder/pytest pids (degraded mode fallback only)

[OUTPUT]
- list_live_e2e_sessions(): deduped sessions for e2e-context + hung reap

[POS]
Dev Gate observability — coordinator 为主 truth source；coordinator 不可用时降级 ps scan。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from e2e_live_chrome_pytest_scan import (  # noqa: PLC0415
    extract_chrome_e2e_test_id,
)
from e2e_stall_guard import node_elapsed_from_snapshot

from e2e_session_runtime.snapshot import (
    admit_elapsed_from_snapshot,
    body_elapsed_from_snapshot,
    prune_stale_session_snapshots,
    read_session_snapshot,
)


@dataclass(frozen=True, slots=True)
class LiveE2ESessionRow:
    pid: int
    test_id: str
    elapsed_sec: float
    state: str
    phase: str
    current_node: str | None = None
    wall_phase: str | None = None
    admit_elapsed_sec: float | None = None
    body_elapsed_sec: float | None = None
    node_elapsed_sec: float | None = None
    batch_mode: bool = False
    shpoib: bool = False
    lane: str = ""


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


def _pid_state_elapsed(pid: int) -> tuple[str, float]:
    try:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "stat=,etime="],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "?", 0.0
    if proc is None or proc.returncode != 0:
        return "?", 0.0
    parts = proc.stdout.strip().split(maxsplit=1)
    if len(parts) == 1:
        return parts[0], 0.0
    state, elapsed = parts
    return state.strip(), _elapsed_to_seconds(elapsed)


def _is_batch_file_invocation(test_id: str) -> bool:
    if "::" in test_id:
        return False
    return " -m " in test_id and "chrome_e2e" in test_id


def _phase_rank(phase: str) -> int:
    order = {"admit": 0, "delegated": 1, "bootstrap": 2, "body": 3, "teardown": 4}
    return order.get(phase.strip().lower(), -1)


def _row_from_snapshot(pid: int, payload: dict[str, object]) -> LiveE2ESessionRow:
    phase = str(payload.get("phase") or "body").strip().lower()
    test_id = str(payload.get("testId") or payload.get("currentNode") or "").strip()
    current_node = str(payload.get("currentNode") or "").strip() or None
    state, elapsed = _pid_state_elapsed(pid)
    return LiveE2ESessionRow(
        pid=pid,
        test_id=test_id or f"pid:{pid}",
        elapsed_sec=elapsed,
        state=state,
        phase=phase,
        current_node=current_node,
        wall_phase=phase,
        admit_elapsed_sec=admit_elapsed_from_snapshot(payload),
        body_elapsed_sec=body_elapsed_from_snapshot(payload),
        node_elapsed_sec=node_elapsed_from_snapshot(payload),
        batch_mode=_is_batch_file_invocation(test_id),
        shpoib=bool(payload.get("shpoib")),
        lane=str(payload.get("lane") or ""),
    )


def _coordinator_has_sessions() -> bool:
    """Check if the Dev Gate coordinator is active and tracking sessions.

    Uses a short direct socket RPC (``snapshot``) instead of ``dev_gate_cli.send`` so
    a congested coordinator cannot trigger send()'s extended timeout-recovery loop
    (~300s+) during orphan-budget / parallel snapshot reads.
    """
    try:
        from dev_gate_cli import (  # noqa: PLC0415
            default_socket_path,
            normalized_socket_path,
        )
        from dev_gate_coordinator import request  # noqa: PLC0415

        socket_path = normalized_socket_path(default_socket_path())
        if not socket_path.exists():
            return False
        result = request(
            {"operation": "snapshot"},
            socket_path=socket_path,
            timeout_sec=3.0,
        )
        return isinstance(result.get("sessions"), list)
    except (ImportError, OSError, RuntimeError, ValueError, TimeoutError):
        return False


def _batch_has_inner_pytest(test_id: str) -> bool:
    """True when a file-batch test.sh already spawned an inner pytest for this file."""
    if "::" in test_id:
        return False
    file_prefix = test_id.split(" -m ", 1)[0].strip()
    if not file_prefix.endswith(".py"):
        return False
    from e2e_live_chrome_pytest_scan import (
        list_live_chrome_e2e_pytest_rows,
    )  # noqa: PLC0415

    for row in list_live_chrome_e2e_pytest_rows():
        inner_id = row.test_id.strip()
        if inner_id.startswith(f"{file_prefix}::"):
            return True
    return False


def _list_test_sh_admit_fallback(
    covered_test_ids: set[str],
) -> tuple[LiveE2ESessionRow, ...]:
    """Fallback for ADMIT test.sh before sidecar write — disabled when coordinator active.

    P0-A: formal flow relies on coordinator + session snapshots, not ps scan.
    ps fallback only activates when coordinator is unreachable (degraded mode).
    """
    if _coordinator_has_sessions():
        return ()
    try:
        proc = subprocess.run(
            ["ps", "-eo", "pid=,stat=,etime=,command="],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return ()
    if proc.returncode != 0:
        return ()
    rows: list[LiveE2ESessionRow] = []
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if "scripts/dev/test.sh" not in stripped:
            continue
        if "chrome_e2e" not in stripped and "tests/e2e/" not in stripped:
            continue
        parts = stripped.split(maxsplit=3)
        if len(parts) < 4:
            continue
        pid_str, state, elapsed, command = parts
        try:
            pid = int(pid_str)
        except ValueError:
            continue
        if read_session_snapshot(pid) is not None:
            continue
        test_id = extract_chrome_e2e_test_id(command)
        if test_id is None:
            continue
        if test_id in covered_test_ids:
            continue
        if _is_batch_file_invocation(test_id) and _batch_has_inner_pytest(test_id):
            continue
        rows.append(
            LiveE2ESessionRow(
                pid=pid,
                test_id=test_id,
                elapsed_sec=_elapsed_to_seconds(elapsed),
                state=state,
                phase="admit",
                current_node="E2E_ADMIT_TEST_SH",
                wall_phase="admit",
                admit_elapsed_sec=_elapsed_to_seconds(elapsed),
                batch_mode=_is_batch_file_invocation(test_id),
                shpoib="E2E_PROFILE_SHPOIB=1" in command
                or "MYRM_E2E_SHPOIB=1" in command,
            )
        )
    return tuple(rows)


def _list_pytest_scan_fallback(
    covered_test_ids: set[str],
) -> tuple[LiveE2ESessionRow, ...]:
    """Live inner pytest rows not yet written to session sidecars (bootstrap/admit gap).

    Closes active_test_count=0 while chrome_e2e pytest is alive but coordinator
    snapshots are not yet visible to e2e-context.
    """
    from e2e_live_chrome_pytest_scan import (
        list_live_chrome_e2e_pytest_rows,
    )  # noqa: PLC0415

    rows: list[LiveE2ESessionRow] = []
    for prow in list_live_chrome_e2e_pytest_rows():
        if prow.is_wrapper:
            continue
        if prow.test_id in covered_test_ids:
            continue
        if read_session_snapshot(prow.pid) is not None:
            continue
        rows.append(
            LiveE2ESessionRow(
                pid=prow.pid,
                test_id=prow.test_id,
                elapsed_sec=prow.elapsed_sec,
                state=prow.state,
                phase="bootstrap",
                current_node="E2E_PYTEST_BOOTSTRAP",
                wall_phase="bootstrap",
                admit_elapsed_sec=prow.elapsed_sec,
                batch_mode=_is_batch_file_invocation(prow.test_id),
            )
        )
    return tuple(rows)


def list_live_e2e_sessions() -> tuple[LiveE2ESessionRow, ...]:
    """Live chrome_e2e sessions from sidecar registry (ADMIT + BODY)."""
    from e2e_session_runtime.snapshot import _load_all_session_snapshots  # noqa: PLC0415

    prune_stale_session_snapshots()
    grouped: dict[str, LiveE2ESessionRow] = {}
    for pid, payload in _load_all_session_snapshots(live_only=True):
        row = _row_from_snapshot(pid, payload)
        key = row.test_id
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = row
            continue
        if _phase_rank(row.phase) > _phase_rank(existing.phase):
            grouped[key] = row
        elif (
            _phase_rank(row.phase) == _phase_rank(existing.phase)
            and row.pid > existing.pid
        ):
            grouped[key] = row
    covered = set(grouped.keys())
    for row in _list_test_sh_admit_fallback(covered):
        grouped.setdefault(row.test_id, row)
        covered.add(row.test_id)
    for row in _list_pytest_scan_fallback(covered):
        grouped.setdefault(row.test_id, row)
    return tuple(sorted(grouped.values(), key=lambda item: (item.test_id, item.pid)))


def admit_active_count(sessions: tuple[LiveE2ESessionRow, ...]) -> int:
    return sum(1 for row in sessions if row.phase in {"admit", "bootstrap"})


def body_active_count(sessions: tuple[LiveE2ESessionRow, ...]) -> int:
    return sum(1 for row in sessions if row.phase == "body")
