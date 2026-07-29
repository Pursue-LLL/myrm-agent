"""Reap excess wave leases when holder pytest processes are gone (R58 hygiene).

[INPUT]
- stack_mutation_policy.wave_active_lease_count (POS: active wave lease tally)
- e2e_session_registry list_live_e2e_sessions (R144/R146 SSOT — ADMIT+BODY sidecar)
- e2e_session_snapshot body_elapsed / progress stall (R62 Phase B)

[OUTPUT]
- maybe_reap_excess_wave_leases: run wave reap when leases exceed live tests + slack
- maybe_reap_hung_chrome_e2e_pytest: SIGINT hung BODY tests + wave reap (body≥600 hard wall · progress_stale≥90 when body<600 · E2E_NODE_STUCK on transport nodes)

[POS]
Admission queue relief — stale/hung leases inflate cap pressure under parallel chrome_e2e.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from e2e_live_chrome_pytest_scan import LiveChromeE2ERow
from e2e_session_registry import LiveE2ESessionRow, list_live_e2e_sessions


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _process_has_signoff_env(pid: int) -> bool:
    try:
        proc = subprocess.run(
            ["ps", "eww", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return False
    if proc.returncode != 0:
        return False
    return "E2E_SIGNOFF=1" in proc.stdout


def _hung_reason_for_row(row: LiveChromeE2ERow) -> str | None:
    if _process_has_signoff_env(row.pid):
        return None
    root = _monorepo_root()
    sys.path.insert(0, str(root / "myrm-agent" / "scripts" / "dev" / "lib"))
    from dev_gate_contract import shpoib_parallel_stall_progress_sec  # noqa: PLC0415

    stall_cap = shpoib_parallel_stall_progress_sec()
    from transport_supervisor import live_agent_pytest_wall_cap_sec  # noqa: PLC0415
    from e2e_session_snapshot import (  # noqa: PLC0415
        body_elapsed_from_snapshot,
        phase_elapsed_from_snapshot,
        progress_stale_sec,
        resolve_session_snapshot,
    )

    snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
    if snapshot is not None:
        phase = str(snapshot.get("phase") or "").strip().lower()
        if phase == "admit":
            from dev_gate_contract import admit_wall_clock_sec  # noqa: PLC0415

            admit_elapsed = phase_elapsed_from_snapshot(snapshot)
            elapsed_for_cap = (
                admit_elapsed if admit_elapsed is not None else row.elapsed_sec
            )
            admit_cap = float(admit_wall_clock_sec())
            if elapsed_for_cap >= admit_cap:
                return (
                    f"admit_elapsed={int(elapsed_for_cap)}s>={int(admit_cap)}s "
                    "(E2E_ADMIT_STALL)"
                )
            return None
        if phase == "bootstrap":
            from transport_supervisor import bootstrap_wall_cap_sec  # noqa: PLC0415

            bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=True))
            bootstrap_elapsed = phase_elapsed_from_snapshot(snapshot)
            elapsed_for_cap = (
                bootstrap_elapsed if bootstrap_elapsed is not None else row.elapsed_sec
            )
            if elapsed_for_cap >= bootstrap_cap:
                return (
                    f"bootstrap_elapsed={int(elapsed_for_cap)}s>={int(bootstrap_cap)}s"
                )
            return None
        body_elapsed = body_elapsed_from_snapshot(snapshot)
        if body_elapsed is not None:
            from dev_gate_contract import (  # noqa: PLC0415
                E2E_BODY_WALL_EXCEEDED_TOKEN,
                LIVE_AGENT_BODY_WALL_CLOCK_SEC,
            )

            body_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
            if body_elapsed >= body_cap:
                return (
                    f"{E2E_BODY_WALL_EXCEEDED_TOKEN}: "
                    f"body_elapsed={int(body_elapsed)}s>={int(body_cap)}s"
                )
            stale = progress_stale_sec(snapshot)
            if stale is not None and stale >= stall_cap:
                return (
                    f"progress_stale={int(stale)}s>={int(stall_cap)}s "
                    f"body_elapsed={int(body_elapsed)}s"
                )
        from e2e_stall_guard import node_stuck_reason_from_snapshot  # noqa: PLC0415

        node_stuck = node_stuck_reason_from_snapshot(snapshot)
        if node_stuck is not None:
            return node_stuck
        stale = progress_stale_sec(snapshot)
        if (
            body_elapsed is not None
            and body_elapsed >= 30.0
            and stale is not None
            and stale >= stall_cap
        ):
            return f"progress_stale={int(stale)}s>={int(stall_cap)}s"
        # R141: healthy body/bootstrap snapshot must not fall through to process_elapsed.
        return None
    if row.elapsed_sec >= float(live_agent_pytest_wall_cap_sec(pessimistic_peers=True)):
        return (
            f"process_elapsed={int(row.elapsed_sec)}s>="
            f"{live_agent_pytest_wall_cap_sec(pessimistic_peers=True)}s"
        )
    return None


def _hung_reason_for_session(row: LiveE2ESessionRow) -> str | None:
    if _process_has_signoff_env(row.pid):
        return None
    chrome_row = LiveChromeE2ERow(
        pid=row.pid,
        elapsed_sec=row.elapsed_sec,
        command=row.test_id,
        test_id=row.test_id,
        state=row.state,
    )
    reason = _hung_reason_for_row(chrome_row)
    if reason is not None:
        return reason
    if row.phase != "admit":
        return None
    from dev_gate_contract import admit_wall_clock_sec  # noqa: PLC0415

    admit_elapsed = (
        row.admit_elapsed_sec if row.admit_elapsed_sec is not None else row.elapsed_sec
    )
    admit_cap = float(admit_wall_clock_sec())
    if admit_elapsed >= admit_cap:
        return (
            f"admit_elapsed={int(admit_elapsed)}s>={int(admit_cap)}s "
            "(E2E_ADMIT_STALL)"
        )
    return None


def _healthy_body_sessions_active(*, skip_pid: int | None = None) -> bool:
    """True when a peer has healthy BODY snapshot — defer wave reap after hung SIGINT."""
    from dev_gate_contract import shpoib_parallel_stall_progress_sec  # noqa: PLC0415
    from e2e_session_snapshot import (  # noqa: PLC0415
        body_elapsed_from_snapshot,
        progress_stale_sec,
        resolve_session_snapshot,
    )
    from e2e_stall_guard import node_stuck_reason_from_snapshot  # noqa: PLC0415

    stall_cap = shpoib_parallel_stall_progress_sec()
    for row in list_live_e2e_sessions():
        if skip_pid is not None and row.pid == skip_pid:
            continue
        if row.phase != "body":
            continue
        snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
        if snapshot is None:
            continue
        body_elapsed = body_elapsed_from_snapshot(snapshot)
        if body_elapsed is None or body_elapsed >= 600.0:
            continue
        if node_stuck_reason_from_snapshot(snapshot) is not None:
            continue
        stale = progress_stale_sec(snapshot)
        if stale is not None and stale >= stall_cap:
            continue
        return True
    return False


def _process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_hung_pytest(pid: int, *, admit_stall: bool) -> bool:
    """Best-effort terminate hung pytest process group; ADMIT stalls use SIGKILL."""
    _ensure_harness_os_compat()
    from myrm_agent_harness.utils.os_compat import (  # noqa: PLC0415
        kill_process_group,
        terminate_process_graceful,
    )

    if admit_stall:
        try:
            kill_process_group(pid, signal.SIGKILL)
        except OSError:
            return False
        time.sleep(0.1)
        return not _process_alive(pid)

    try:
        terminate_process_graceful(pid, grace_seconds=1.0)
    except OSError:
        return False
    return not _process_alive(pid)


def _ensure_harness_os_compat() -> None:
    root = _monorepo_root()
    harness_src = root / "myrm-agent-harness" / "src"
    if harness_src.is_dir() and str(harness_src) not in sys.path:
        sys.path.insert(0, str(harness_src))


def maybe_reap_hung_chrome_e2e_pytest(*, skip_pid: int | None = None) -> bool:
    """SIGINT pytest processes exceeding BODY budget or progress stall; then wave reap."""
    reaped = False
    for row in list_live_e2e_sessions():
        if skip_pid is not None and row.pid == skip_pid:
            continue
        reason = _hung_reason_for_session(row)
        if reason is None:
            continue
        print(
            f"E2E_HUNG_PYTEST_REAP: pid={row.pid} test={row.test_id} reason={reason} "
            "(do not stop other pytest)",
            file=sys.stderr,
            flush=True,
        )
        admit_stall = "E2E_ADMIT_STALL" in reason
        if not _terminate_hung_pytest(row.pid, admit_stall=admit_stall):
            continue
        reaped = True
        time.sleep(0.5)
    if not reaped:
        return False
    if _healthy_body_sessions_active(skip_pid=skip_pid):
        print(
            "E2E_HUNG_REAP_DEFER_WAVE: healthy BODY peers active; skip wave reap "
            "(do not stop other pytest)",
            file=sys.stderr,
            flush=True,
        )
        return True
    wave_bin = _monorepo_root() / "myrm-agent" / "scripts" / "dev" / "wave.sh"
    subprocess.run(["bash", str(wave_bin), "reap"], check=False, env=os.environ.copy())
    return True


def maybe_reap_excess_wave_leases(*, slack: int = 2) -> bool:
    """Return True when an extra wave reap was triggered."""
    maybe_reap_hung_chrome_e2e_pytest()
    try:
        from e2e_session_snapshot import prune_stale_session_snapshots

        prune_stale_session_snapshots()
    except ImportError:
        pass
    root = _monorepo_root()
    sys.path.insert(0, str(root / "myrm-agent" / "scripts" / "dev" / "lib"))
    from stack_mutation_policy import wave_active_lease_count

    active_leases = wave_active_lease_count(root)
    active_tests = len(list_live_e2e_sessions())
    threshold = active_tests + max(0, int(slack))
    if active_leases <= threshold:
        return False
    wave_bin = root / "myrm-agent" / "scripts" / "dev" / "wave.sh"
    print(
        f"E2E_STALE_LEASE_REAP: wave_leases={active_leases} "
        f"active_tests={active_tests} threshold={threshold} "
        "(do not stop other pytest)",
        file=sys.stderr,
        flush=True,
    )
    env = os.environ.copy()
    subprocess.run(
        ["bash", str(wave_bin), "reap"],
        check=False,
        env=env,
    )
    return True
