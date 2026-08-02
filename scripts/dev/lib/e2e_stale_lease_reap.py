"""Reap excess wave leases when holder pytest processes are gone (R58 hygiene).

[INPUT]
- stack_mutation_policy.wave_active_lease_count (POS: active wave lease tally)
- e2e_session_registry list_live_e2e_sessions (R144/R146 SSOT — ADMIT+BODY sidecar)
- e2e_session_snapshot body_elapsed / progress stall (R62 Phase B)

[OUTPUT]
- maybe_reap_excess_wave_leases: run wave reap when leases exceed live tests + slack
- maybe_reap_hung_chrome_e2e_pytest: SIGINT hung BODY tests + wave reap (body≥600 hard wall · progress_stale≥90 when body<600 · E2E_NODE_STUCK on transport nodes)
- maybe_reap_stale_heartbeat_leases: expire hb-stale leases (dead owner · no linked pytest · linked without healthy BODY)

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


def _coordinator_reap_authorized() -> bool:
    """P0-A: peer SIGINT/reap is coordinator-only; status/readiness paths must not call reapers."""
    return os.environ.get("MYRM_DEV_GATE_COORDINATOR_REAP", "").strip() == "1"


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _process_ps_environ(pid: int) -> str:
    try:
        proc = subprocess.run(
            ["ps", "eww", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    if proc is None or proc.returncode != 0:
        return ""
    return proc.stdout


def _process_has_signoff_env(pid: int) -> bool:
    return "E2E_SIGNOFF=1" in _process_ps_environ(pid)


def _process_has_desktop_soak_env(pid: int) -> bool:
    return "MYRM_E2E_DESKTOP_SOAK=1" in _process_ps_environ(pid)


def _process_env_value(pid: int, key: str) -> str | None:
    prefix = f"{key}="
    for token in _process_ps_environ(pid).split():
        if token.startswith(prefix):
            return token[len(prefix) :]
    return None


def _with_process_signoff_budget_env(pid: int):
    """Temporarily mirror signoff + desktop soak BODY env from target pytest for SSOT caps."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        keys = (
            "E2E_SIGNOFF",
            "MYRM_E2E_SIGNOFF_BATCH_BODY_SEC",
            "MYRM_E2E_DESKTOP_SOAK",
        )
        prior = {key: os.environ.get(key) for key in keys}
        try:
            if _process_has_signoff_env(pid):
                os.environ["E2E_SIGNOFF"] = "1"
                batch_body = _process_env_value(pid, "MYRM_E2E_SIGNOFF_BATCH_BODY_SEC")
                if batch_body:
                    os.environ["MYRM_E2E_SIGNOFF_BATCH_BODY_SEC"] = batch_body
                desktop_soak = _process_env_value(pid, "MYRM_E2E_DESKTOP_SOAK")
                if desktop_soak:
                    os.environ["MYRM_E2E_DESKTOP_SOAK"] = desktop_soak
            yield
        finally:
            for key, value in prior.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    return _ctx()


def _body_wall_cap_for_pid(pid: int) -> float:
    """BODY hung-reap cap aligned with resolve_budget_policy SSOT (incl. batch BODY sec)."""
    if not _process_has_signoff_env(pid):
        try:
            from transport_supervisor import live_agent_body_wall_cap_sec

            return float(live_agent_body_wall_cap_sec())
        except ImportError:
            from dev_gate_contract import LIVE_AGENT_BODY_WALL_CLOCK_SEC

            return float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
    with _with_process_signoff_budget_env(pid):
        from e2e_session_lifecycle import resolve_budget_policy  # noqa: PLC0415

        return float(resolve_budget_policy().body_sec)


def _admit_wall_cap_for_pid(pid: int) -> float:
    """ADMIT hung-reap cap aligned with admit_wall_clock_sec SSOT."""
    import os

    from dev_gate_contract import admit_wall_clock_sec  # noqa: PLC0415

    if _process_has_signoff_env(pid):
        prior = os.environ.get("E2E_SIGNOFF")
        os.environ["E2E_SIGNOFF"] = "1"
        try:
            return float(admit_wall_clock_sec())
        finally:
            if prior is None:
                os.environ.pop("E2E_SIGNOFF", None)
            else:
                os.environ["E2E_SIGNOFF"] = prior
    return float(admit_wall_clock_sec())


def _hung_reason_for_row(row: LiveChromeE2ERow) -> str | None:
    signoff = _process_has_signoff_env(row.pid)
    root = _monorepo_root()
    sys.path.insert(0, str(root / "myrm-agent" / "scripts" / "dev" / "lib"))
    from dev_gate_contract import shpoib_parallel_stall_progress_sec  # noqa: PLC0415

    stall_cap = shpoib_parallel_stall_progress_sec()
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
            admit_elapsed = phase_elapsed_from_snapshot(snapshot)
            elapsed_for_cap = (
                admit_elapsed if admit_elapsed is not None else row.elapsed_sec
            )
            if signoff and row.test_id:
                from e2e_session_snapshot import (  # noqa: PLC0415
                    read_session_snapshot_by_test_id,
                )

                child_match = read_session_snapshot_by_test_id(row.test_id)
                if child_match is not None:
                    child_phase = str(child_match[1].get("phase") or "").strip().lower()
                    if child_phase in ("bootstrap", "body"):
                        return None
            admit_cap = _admit_wall_cap_for_pid(row.pid)
            if elapsed_for_cap >= admit_cap:
                return (
                    f"admit_elapsed={int(elapsed_for_cap)}s>={int(admit_cap)}s "
                    "(E2E_ADMIT_STALL)"
                )
            return None
        if phase == "body":
            body_elapsed_hard = body_elapsed_from_snapshot(snapshot)
            if body_elapsed_hard is not None:
                from dev_gate_contract import (
                    E2E_BODY_WALL_EXCEEDED_TOKEN,
                )  # noqa: PLC0415

                body_cap = _body_wall_cap_for_pid(row.pid)
                if body_elapsed_hard >= body_cap:
                    return (
                        f"{E2E_BODY_WALL_EXCEEDED_TOKEN}: "
                        f"body_elapsed={int(body_elapsed_hard)}s>={int(body_cap)}s"
                    )
            from e2e_stall_guard import node_stuck_reason_from_snapshot  # noqa: PLC0415

            node_stuck = node_stuck_reason_from_snapshot(snapshot)
            if node_stuck is not None:
                return node_stuck
        if phase == "bootstrap":
            if signoff:
                from dev_gate_contract import (
                    signoff_effective_bootstrap_wall_sec,
                )  # noqa: PLC0415

                bootstrap_cap = signoff_effective_bootstrap_wall_sec()
            else:
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
            if signoff:
                from e2e_stall_guard import (
                    node_stuck_reason_from_snapshot,
                )  # noqa: PLC0415

                node_stuck = node_stuck_reason_from_snapshot(snapshot)
                if node_stuck is not None:
                    return node_stuck
                return None
            return None
        if signoff:
            # Signoff: defer progress_stale only — bootstrap/body caps handled above (R187).
            return None
        body_elapsed = body_elapsed_from_snapshot(snapshot)
        if body_elapsed is not None:
            from dev_gate_contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415

            body_cap = _body_wall_cap_for_pid(row.pid)
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
    from dev_gate_contract import LIVE_AGENT_PYTEST_WALL_CAP_SEC  # noqa: PLC0415

    if row.elapsed_sec >= float(LIVE_AGENT_PYTEST_WALL_CAP_SEC):
        return (
            f"process_elapsed={int(row.elapsed_sec)}s>="
            f"{LIVE_AGENT_PYTEST_WALL_CAP_SEC}s"
        )
    return None


def _parallel_node_stuck_reason(row: LiveE2ESessionRow) -> str | None:
    """Align hung-reap with e2e-context FAIL_FAST when sidecar snapshot lags."""
    node_elapsed = row.node_elapsed_sec
    if node_elapsed is None:
        return None
    from dev_gate_contract import (  # noqa: PLC0415
        NODE_STUCK_FAIL_FAST_SEC,
        resolve_transport_stall_cap_sec,
    )
    from e2e_stall_guard import is_transport_stall_node  # noqa: PLC0415

    current_node = str(row.current_node or "").strip()
    elapsed_f = float(node_elapsed)
    wall = str(row.wall_phase or row.phase or "").strip().lower()
    if wall == "admit":
        if elapsed_f < _admit_wall_cap_for_pid(row.pid):
            return None
    if wall == "body":
        if elapsed_f < _body_wall_cap_for_pid(row.pid):
            return None
    if wall == "bootstrap":
        if _process_has_signoff_env(row.pid):
            from dev_gate_contract import (
                signoff_effective_bootstrap_wall_sec,
            )  # noqa: PLC0415

            bootstrap_cap = signoff_effective_bootstrap_wall_sec()
        else:
            from transport_supervisor import bootstrap_wall_cap_sec  # noqa: PLC0415

            bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=True))
        if elapsed_f < bootstrap_cap:
            return None
    if current_node and is_transport_stall_node(current_node):
        stall_cap = float(resolve_transport_stall_cap_sec(current_node=current_node))
        if elapsed_f >= stall_cap:
            return (
                f"E2E_NODE_STUCK: parallel node={current_node!r} "
                f"node_elapsed={int(elapsed_f)}s>={int(stall_cap)}s"
            )
        return None
    if elapsed_f >= float(NODE_STUCK_FAIL_FAST_SEC):
        node_label = current_node or "?"
        return (
            f"E2E_NODE_STUCK: parallel node={node_label!r} "
            f"node_elapsed={int(elapsed_f)}s>={int(NODE_STUCK_FAIL_FAST_SEC)}s"
        )
    return None


def _hung_reason_for_session(row: LiveE2ESessionRow) -> str | None:
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
    parallel_stuck = _parallel_node_stuck_reason(row)
    if parallel_stuck is not None:
        return parallel_stuck
    wall = str(row.wall_phase or row.phase or "").strip().lower()
    if wall == "bootstrap":
        if _process_has_signoff_env(row.pid):
            from dev_gate_contract import (
                signoff_effective_bootstrap_wall_sec,
            )  # noqa: PLC0415

            bootstrap_cap = signoff_effective_bootstrap_wall_sec()
        else:
            from transport_supervisor import bootstrap_wall_cap_sec  # noqa: PLC0415

            bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=True))
        bootstrap_elapsed = row.node_elapsed_sec
        if bootstrap_elapsed is None:
            bootstrap_elapsed = row.elapsed_sec
        if float(bootstrap_elapsed) >= bootstrap_cap:
            return f"bootstrap_elapsed={int(bootstrap_elapsed)}s>={int(bootstrap_cap)}s"
    if row.phase != "admit":
        return None

    admit_elapsed = (
        row.admit_elapsed_sec if row.admit_elapsed_sec is not None else row.elapsed_sec
    )
    admit_cap = _admit_wall_cap_for_pid(row.pid)
    if admit_elapsed >= admit_cap:
        return (
            f"admit_elapsed={int(admit_elapsed)}s>={int(admit_cap)}s "
            "(E2E_ADMIT_STALL)"
        )
    return None


def _session_row_is_healthy_body(row: LiveE2ESessionRow) -> bool:
    """True when session has fresh BODY progress (peer defer guard)."""
    from dev_gate_contract import shpoib_parallel_stall_progress_sec  # noqa: PLC0415
    from e2e_session_snapshot import (  # noqa: PLC0415
        body_elapsed_from_snapshot,
        progress_stale_sec,
        resolve_session_snapshot,
    )
    from e2e_stall_guard import node_stuck_reason_from_snapshot  # noqa: PLC0415

    if row.phase != "body":
        return False
    snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
    if snapshot is None:
        return False
    body_elapsed = body_elapsed_from_snapshot(snapshot)
    body_cap = _body_wall_cap_for_pid(row.pid)
    if body_elapsed is None or body_elapsed >= body_cap:
        return False
    if node_stuck_reason_from_snapshot(snapshot) is not None:
        return False
    stale = progress_stale_sec(snapshot)
    stall_cap = shpoib_parallel_stall_progress_sec()
    if stale is not None and stale >= stall_cap:
        return False
    return True


def _linked_pytest_has_healthy_body(linked_pytest: str) -> bool:
    for row in list_live_e2e_sessions():
        if row.test_id != linked_pytest:
            continue
        return _session_row_is_healthy_body(row)
    return False


def _healthy_body_sessions_active(*, skip_pid: int | None = None) -> bool:
    """True when a peer has healthy BODY snapshot — defer wave reap after hung SIGINT."""
    for row in list_live_e2e_sessions():
        if skip_pid is not None and row.pid == skip_pid:
            continue
        if _session_row_is_healthy_body(row):
            return True
    return False


def maybe_reap_stale_heartbeat_leases() -> bool:
    """Expire heartbeat-stale leases with no linked pytest or dead owner."""
    if not _coordinator_reap_authorized():
        return False
    from dev_gate_contract import E2E_STALE_HEARTBEAT_REAP_SEC  # noqa: PLC0415
    from e2e_lease_liveness import (
        build_lease_liveness,
        load_wave_snapshot,
    )  # noqa: PLC0415

    active_tests = [
        {"pid": row.pid, "test_id": row.test_id} for row in list_live_e2e_sessions()
    ]
    rows = build_lease_liveness(load_wave_snapshot(), active_tests=active_tests)
    reaped = False
    dev_dir = _monorepo_root() / "myrm-agent" / "scripts" / "dev"
    if str(dev_dir) not in sys.path:
        sys.path.insert(0, str(dev_dir))
    from wave_orchestrator.core import expire_lease_watchdog  # noqa: PLC0415

    for row in rows:
        if not row.lease_id:
            continue
        hb_age = row.heartbeat_age_sec
        if hb_age is None or hb_age < E2E_STALE_HEARTBEAT_REAP_SEC:
            continue
        if row.owner_alive and row.linked_pytest is not None:
            if _linked_pytest_has_healthy_body(row.linked_pytest):
                continue
        print(
            f"E2E_STALE_HEARTBEAT_REAP: lease={row.lease_id[:8]} "
            f"hb_age={hb_age}s owner_alive={'yes' if row.owner_alive else 'no'} "
            f"linked_pytest={row.linked_pytest or 'none'} "
            "(do not stop other pytest)",
            file=sys.stderr,
            flush=True,
        )
        if expire_lease_watchdog(row.lease_id):
            reaped = True
    return reaped


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


def _reload_stall_guard_ssot() -> None:
    """R170c: long-lived peer pytest must not cross-reap with stale stall caps."""
    import importlib

    import dev_gate_contract
    import e2e_stall_guard

    importlib.reload(dev_gate_contract)
    importlib.reload(e2e_stall_guard)


def _signoff_runner_active() -> bool:
    """True when e2e-m3-signoff.sh holds lockdir pid (parallel peer friend-immunity guard)."""
    lock_dir = Path("/tmp/e2e-m3-signoff.lockdir")
    pid_file = lock_dir / "pid"
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _desktop_soak_runner_active() -> bool:
    """True when e2e-m3-leg-soak.sh desktop holds singleton pid."""
    lock_dir = Path("/tmp/e2e-m3-leg-soak-desktop.singleton.lock.d")
    pid_file = lock_dir / "pid"
    if not pid_file.is_file():
        return False
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _desktop_soak_reap_immunity(row: LiveE2ESessionRow, reason: str) -> bool:
    """Skip false-positive hung-reap on desktop soak pytest (HITL/mux waits > NODE_STUCK)."""
    if not _process_has_desktop_soak_env(row.pid):
        return False
    if reason.startswith(("bootstrap_elapsed=", "admit_elapsed=")):
        return False
    from dev_gate_contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415

    if E2E_BODY_WALL_EXCEEDED_TOKEN in reason:
        # R250: hung-reap must not SIGINT desktop soak at legacy 600s BODY cap.
        return True
    if reason.startswith("E2E_NODE_STUCK"):
        return True
    if reason.startswith("progress_stale="):
        return True
    if reason.startswith("process_elapsed=") and row.phase == "body":
        return True
    return False


def _signoff_peer_reap_immunity(row: LiveE2ESessionRow, reason: str) -> bool:
    """Skip hung-reap on healthy parallel peers while signoff runner is active."""
    if not _signoff_runner_active():
        return False
    if _process_has_signoff_env(row.pid):
        return False
    # R198: hard-cap ADMIT/BOOTSTRAP breaches must reap even during signoff.
    if reason.startswith(("bootstrap_elapsed=", "admit_elapsed=")):
        return False
    if reason.startswith("E2E_NODE_STUCK"):
        return False
    if _parallel_node_stuck_reason(row) is not None:
        return False
    if _session_row_is_healthy_body(row):
        return True
    if not reason.startswith("process_elapsed="):
        return False
    if row.phase != "body":
        return False
    try:
        from e2e_session_snapshot import resolve_session_snapshot  # noqa: PLC0415
    except ImportError:
        return False
    snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
    return snapshot is not None


def maybe_reap_hung_chrome_e2e_pytest(*, skip_pid: int | None = None) -> bool:
    """SIGINT pytest processes exceeding BODY budget or progress stall; then wave reap."""
    if not _coordinator_reap_authorized():
        return False
    _reload_stall_guard_ssot()
    reaped = False
    for row in list_live_e2e_sessions():
        if skip_pid is not None and row.pid == skip_pid:
            continue
        reason = _hung_reason_for_session(row)
        if reason is None:
            continue
        if _signoff_peer_reap_immunity(row, reason):
            print(
                f"E2E_HUNG_REAP_SKIP_SIGNOFF_FRIEND: pid={row.pid} test={row.test_id} "
                f"reason={reason} (signoff runner active; do not stop other pytest)",
                file=sys.stderr,
                flush=True,
            )
            continue
        if _desktop_soak_reap_immunity(row, reason):
            print(
                f"E2E_HUNG_REAP_SKIP_DESKTOP_SOAK: pid={row.pid} test={row.test_id} "
                f"reason={reason} (desktop soak BODY; do not stop other pytest)",
                file=sys.stderr,
                flush=True,
            )
            continue
        print(
            f"E2E_HUNG_PYTEST_REAP: pid={row.pid} test={row.test_id} reason={reason} "
            "(do not stop other pytest)",
            file=sys.stderr,
            flush=True,
        )
        from dev_gate_contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415

        force_kill = (
            "E2E_ADMIT_STALL" in reason
            or E2E_BODY_WALL_EXCEEDED_TOKEN in reason
            or reason.startswith("bootstrap_elapsed=")
        )
        if not _terminate_hung_pytest(row.pid, admit_stall=force_kill):
            continue
        reaped = True
        time.sleep(0.5)
    if not reaped:
        return False
    other_sessions = [
        row
        for row in list_live_e2e_sessions()
        if skip_pid is None or row.pid != skip_pid
    ]
    if other_sessions or _healthy_body_sessions_active(skip_pid=skip_pid):
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
    if not _coordinator_reap_authorized():
        return False
    maybe_reap_hung_chrome_e2e_pytest()
    try:
        from e2e_session_snapshot import prune_stale_session_snapshots

        prune_stale_session_snapshots()
    except ImportError:
        pass
    root = _monorepo_root()
    sys.path.insert(0, str(root / "myrm-agent" / "scripts" / "dev" / "lib"))
    from e2e_lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )  # noqa: PLC0415

    counts = wave_lease_counts(load_wave_snapshot())
    active_leases = counts.effective_total
    active_tests = len(list_live_e2e_sessions())
    threshold = active_tests + max(0, int(slack))
    if active_leases <= threshold:
        return False
    wave_bin = root / "myrm-agent" / "scripts" / "dev" / "wave.sh"
    print(
        f"E2E_STALE_LEASE_REAP: wave_leases_effective={active_leases} "
        f"wave_leases_raw={counts.total} "
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
