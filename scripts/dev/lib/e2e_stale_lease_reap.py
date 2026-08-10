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

import json
import os
import signal
import sqlite3
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


def _pytest_timeout_sec_for_pid(pid: int) -> int | None:
    """Parse pytest --timeout=N from live process command."""
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    import re

    match = re.search(r"--timeout(?:=|\s+)(\d+)", result.stdout)
    if match is None:
        return None
    return int(match.group(1))


def _body_wall_cap_for_pid(pid: int) -> float:
    """BODY hung-reap cap aligned with resolve_budget_policy SSOT (incl. batch BODY sec)."""
    if _process_has_desktop_soak_env(pid):
        pytest_cap = _pytest_timeout_sec_for_pid(pid)
        if pytest_cap is not None:
            return float(pytest_cap)
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


def _hung_reason_for_row(
    row: LiveChromeE2ERow,
    *,
    admit_elapsed_sec: float | None = None,
) -> str | None:
    signoff = _process_has_signoff_env(row.pid)
    root = _monorepo_root()
    sys.path.insert(0, str(root / "myrm-agent" / "scripts" / "dev" / "lib"))
    from dev_gate_contract import shpoib_parallel_stall_progress_sec  # noqa: PLC0415
    from e2e_session_snapshot import (  # noqa: PLC0415
        body_elapsed_from_snapshot,
        phase_elapsed_from_snapshot,
        progress_stale_sec,
        resolve_session_snapshot,
    )

    snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
    if snapshot is not None:
        phase = str(snapshot.get("phase") or "").strip().lower()
        if phase == "delegated":
            return None
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
                    if child_phase in ("bootstrap", "body", "delegated"):
                        return None
            from e2e_stall_guard import (  # noqa: PLC0415
                admit_node_stuck_reason_from_snapshot,
            )

            admit_node_stuck = admit_node_stuck_reason_from_snapshot(snapshot)
            if admit_node_stuck is not None:
                return admit_node_stuck
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
            from dev_gate_contract import (  # noqa: PLC0415
                dev_bootstrap_wall_cap_for_hung_reap,
            )

            lane = str(snapshot.get("lane") or "").strip().upper() or "RESOURCE_WRITE"
            shpoib = snapshot.get("shpoib") is True
            bootstrap_cap = dev_bootstrap_wall_cap_for_hung_reap(
                lane=lane,
                shpoib=shpoib,
            )
            if signoff:
                from dev_gate_contract import (  # noqa: PLC0415
                    signoff_effective_bootstrap_wall_sec,
                )

                bootstrap_cap = max(
                    bootstrap_cap,
                    signoff_effective_bootstrap_wall_sec(),
                )
            snapshot_cap = snapshot.get("phaseCapSec")
            if isinstance(snapshot_cap, (int, float)) and float(snapshot_cap) > 0:
                bootstrap_cap = max(bootstrap_cap, float(snapshot_cap))
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
            from e2e_stall_guard import node_stuck_reason_from_snapshot  # noqa: PLC0415

            node_stuck = node_stuck_reason_from_snapshot(snapshot)
            if node_stuck is not None:
                return node_stuck
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
            stall_cap = shpoib_parallel_stall_progress_sec(
                lane=str(snapshot.get("lane") or ""),
                workload=str(snapshot.get("workload") or ""),
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
        stall_cap = shpoib_parallel_stall_progress_sec(
            lane=str(snapshot.get("lane") or ""),
            workload=str(snapshot.get("workload") or ""),
        )
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

    effective_elapsed = float(row.elapsed_sec)
    if admit_elapsed_sec is not None:
        effective_elapsed = max(0.0, effective_elapsed - float(admit_elapsed_sec))
    if effective_elapsed >= float(LIVE_AGENT_PYTEST_WALL_CAP_SEC):
        return (
            f"process_elapsed={int(effective_elapsed)}s>="
            f"{LIVE_AGENT_PYTEST_WALL_CAP_SEC}s"
        )
    return None


def _private_admit_row_for_owner_pid(pid: int) -> sqlite3.Row | None:
    try:
        from dev_gate_store import DevGateStore, default_store_path  # noqa: PLC0415
    except ImportError:
        return None
    try:
        store = DevGateStore(default_store_path())
        with store._connect() as connection:
            return connection.execute(
                """
                SELECT pa.granted_at, pa.released_at, s.state
                FROM sessions s
                JOIN private_admission pa ON pa.session_id = s.session_id
                WHERE s.owner_pid = ?
                  AND pa.released_at IS NULL
                ORDER BY pa.enqueued_at DESC
                LIMIT 1
                """,
                (pid,),
            ).fetchone()
    except (OSError, sqlite3.Error):
        return None


def _private_credit_queue_has_waiters() -> bool:
    try:
        from dev_gate_store import DevGateStore, default_store_path  # noqa: PLC0415
    except ImportError:
        return False
    try:
        store = DevGateStore(default_store_path())
        with store._connect() as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS waiting
                FROM private_admission
                WHERE granted_at IS NULL
                  AND released_at IS NULL
                """
            ).fetchone()
    except (OSError, sqlite3.Error):
        return False
    if row is None:
        return False
    return int(row["waiting"]) > 0


def _holder_waiting_private_admit_credit(pid: int) -> bool:
    """True when holder is queued for PRIVATE credit (granted_at unset), not stuck holding it."""
    row = _private_admit_row_for_owner_pid(pid)
    if row is None:
        return False
    from dev_gate_session import SessionState  # noqa: PLC0415

    state = str(row["state"])
    return state == SessionState.PRIVATE_ADMIT.value and row["granted_at"] is None


def _private_credit_granted_owner_pids() -> frozenset[int]:
    """Owner pids for sessions holding granted (unreleased) private admission credit."""
    try:
        from dev_gate_store import DevGateStore, default_store_path  # noqa: PLC0415
    except ImportError:
        return frozenset()
    try:
        store = DevGateStore(default_store_path())
        with store._connect() as connection:
            rows = connection.execute(
                """
                SELECT s.owner_pid
                FROM private_admission pa
                JOIN sessions s ON s.session_id = pa.session_id
                WHERE pa.granted_at IS NOT NULL
                  AND pa.released_at IS NULL
                  AND s.state NOT IN ('SUCCEEDED', 'FAILED', 'CANCELLED')
                """
            ).fetchall()
    except (OSError, sqlite3.Error):
        return frozenset()
    owners: set[int] = set()
    for row in rows:
        owner_pid = row["owner_pid"]
        if isinstance(owner_pid, int) and owner_pid > 0:
            owners.add(owner_pid)
    return frozenset(owners)


def _pid_in_private_credit_holder_tree(pid: int) -> bool:
    """True when pid is the credit owner or lives under an owner process tree."""
    owners = _private_credit_granted_owner_pids()
    if not owners:
        return False
    if pid in owners:
        return True
    try:
        from process_identity import _descendant_pids  # noqa: PLC0415
    except ImportError:
        return False
    for owner_pid in owners:
        if pid in _descendant_pids(owner_pid):
            return True
        if owner_pid in _descendant_pids(pid):
            return True
    return False


def _holder_holds_private_admit_credit(pid: int) -> bool:
    """True when holder was granted PRIVATE credit and has not released it."""
    row = _private_admit_row_for_owner_pid(pid)
    if row is not None and row["granted_at"] is not None:
        return True
    return _pid_in_private_credit_holder_tree(pid)


def _admit_semantic_node_stuck_reason(row: LiveE2ESessionRow) -> str | None:
    """Node-level ADMIT stall for sidecar-less test.sh holders and batch parents."""
    from dev_gate_contract import (  # noqa: PLC0415
        E2E_ADMIT_NODE_STUCK_TOKEN,
        admit_semantic_node_stall_cap_sec,
        is_admit_semantic_stall_node,
    )

    try:
        from e2e_pytest_dedupe import _holder_process_tree_has_pytest  # noqa: PLC0415
    except ImportError:
        pass
    else:
        if _holder_process_tree_has_pytest(row.pid):
            return None

    current_node = str(row.current_node or "").strip()
    try:
        from e2e_session_snapshot import (  # noqa: PLC0415
            progress_stale_sec,
            resolve_session_snapshot,
        )
    except ImportError:
        pass
    else:
        snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
        if snapshot is not None:
            snap_phase = str(snapshot.get("phase") or "").strip().lower()
            if snap_phase == "delegated":
                return None
            stale = progress_stale_sec(snapshot)
            if stale is not None and stale < 180.0:
                return None
            snap_node = str(snapshot.get("currentNode") or "").strip()
            if snap_node:
                current_node = snap_node
            if current_node == "E2E_PYTEST_SUBPROCESS" or current_node.startswith(
                "E2E_PYTEST"
            ):
                return None
    if not is_admit_semantic_stall_node(current_node):
        return None
    node_elapsed = row.node_elapsed_sec
    if node_elapsed is None:
        node_elapsed = row.admit_elapsed_sec
    if node_elapsed is None:
        node_elapsed = row.elapsed_sec
    signoff = _process_has_signoff_env(row.pid)
    cap = admit_semantic_node_stall_cap_sec(
        current_node=current_node,
        batch_mode=row.batch_mode,
        signoff=signoff,
    )
    admit_wall = _admit_wall_cap_for_pid(row.pid)
    if cap >= admit_wall:
        return None
    if _holder_waiting_private_admit_credit(row.pid):
        return None
    if (
        not _holder_holds_private_admit_credit(row.pid)
        and _private_credit_queue_has_waiters()
    ):
        from dev_gate_contract import E2E_ADMISSION_WALL_CLOCK_SEC  # noqa: PLC0415

        admit_wall = float(E2E_ADMISSION_WALL_CLOCK_SEC)
        elapsed_for_wall = row.admit_elapsed_sec
        if elapsed_for_wall is None:
            elapsed_for_wall = row.node_elapsed_sec
        if elapsed_for_wall is None:
            elapsed_for_wall = row.elapsed_sec
        if float(elapsed_for_wall) < admit_wall:
            return None
    elapsed_f = float(node_elapsed)
    if elapsed_f >= cap:
        return (
            f"{E2E_ADMIT_NODE_STUCK_TOKEN}: node={current_node!r} "
            f"node_elapsed={int(elapsed_f)}s>={int(cap)}s"
        )
    return None


def _parallel_node_stuck_reason(row: LiveE2ESessionRow) -> str | None:
    """Align hung-reap with e2e-context FAIL_FAST when sidecar snapshot lags."""
    node_elapsed = row.node_elapsed_sec
    if node_elapsed is None:
        return None
    from dev_gate_contract import (  # noqa: PLC0415
        E2E_ADMIT_NODE_STUCK_TOKEN,
        NODE_STUCK_FAIL_FAST_SEC,
        is_admit_semantic_stall_node,
        resolve_transport_stall_cap_sec,
    )
    from e2e_stall_guard import is_transport_stall_node  # noqa: PLC0415

    current_node = str(row.current_node or "").strip()
    elapsed_f = float(node_elapsed)
    wall = str(row.wall_phase or row.phase or "").strip().lower()
    if wall == "admit":
        admit_semantic = _admit_semantic_node_stuck_reason(row)
        if admit_semantic is not None:
            return admit_semantic
        if elapsed_f < _admit_wall_cap_for_pid(row.pid):
            return None
        # R285: ADMIT semantic node past the admit wall must keep the ADMIT
        # token (not fall through to generic E2E_NODE_STUCK) so force-kill and
        # signoff peer immunity classification stay aligned with e2e-context.
        if is_admit_semantic_stall_node(current_node):
            wall_sec = int(_admit_wall_cap_for_pid(row.pid))
            return (
                f"{E2E_ADMIT_NODE_STUCK_TOKEN}: node={current_node!r} "
                f"node_elapsed={int(elapsed_f)}s>={wall_sec}s"
            )
    if wall == "body":
        if elapsed_f < _body_wall_cap_for_pid(row.pid):
            return None
    if wall == "bootstrap":
        from dev_gate_contract import (  # noqa: PLC0415
            BOOTSTRAP_CREDIT_HOG_NODE_NAMES,
            BOOTSTRAP_CREDIT_HOG_PROCESS_CAP_SEC,
            E2E_BOOTSTRAP_CREDIT_HOG_TOKEN,
            NODE_STUCK_FAIL_FAST_SEC,
        )

        if (
            _holder_holds_private_admit_credit(row.pid)
            and _private_credit_queue_has_waiters()
        ):
            process_elapsed = float(row.elapsed_sec)
            hog_by_process = process_elapsed >= float(
                BOOTSTRAP_CREDIT_HOG_PROCESS_CAP_SEC
            )
            hog_by_node = (
                current_node in BOOTSTRAP_CREDIT_HOG_NODE_NAMES
                and elapsed_f >= float(NODE_STUCK_FAIL_FAST_SEC)
            )
            if hog_by_process or hog_by_node:
                hog_kind = "process_elapsed" if hog_by_process else "node_elapsed"
                hog_value = int(process_elapsed) if hog_by_process else int(elapsed_f)
                return (
                    f"{E2E_BOOTSTRAP_CREDIT_HOG_TOKEN}: holder pid={row.pid} "
                    f"node={current_node!r} {hog_kind}={hog_value}s "
                    f"while private_credit_queue waiting"
                )
        if _process_has_signoff_env(row.pid):
            from dev_gate_contract import (
                signoff_effective_bootstrap_wall_sec,
            )  # noqa: PLC0415

            bootstrap_cap = signoff_effective_bootstrap_wall_sec()
        else:
            from dev_gate_contract import (
                dev_bootstrap_wall_cap_for_hung_reap,
            )  # noqa: PLC0415

            lane = str(row.lane or "RESOURCE_WRITE").strip().upper() or "RESOURCE_WRITE"
            bootstrap_cap = dev_bootstrap_wall_cap_for_hung_reap(
                lane=lane,
                shpoib=bool(row.shpoib),
            )
        if current_node and is_transport_stall_node(current_node):
            stall_cap = float(
                resolve_transport_stall_cap_sec(current_node=current_node)
            )
            if elapsed_f >= stall_cap:
                return (
                    f"E2E_NODE_STUCK: parallel node={current_node!r} "
                    f"node_elapsed={int(elapsed_f)}s>={int(stall_cap)}s"
                )
            return None
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
    if wall == "delegated" or current_node == "E2E_PYTEST_SUBPROCESS":
        return None
    if elapsed_f >= float(NODE_STUCK_FAIL_FAST_SEC):
        node_label = current_node or "?"
        return (
            f"E2E_NODE_STUCK: parallel node={node_label!r} "
            f"node_elapsed={int(elapsed_f)}s>={int(NODE_STUCK_FAIL_FAST_SEC)}s"
        )
    return None


def _hung_reason_for_session(row: LiveE2ESessionRow) -> str | None:
    if row.phase == "delegated":
        return None
    try:
        from e2e_pytest_dedupe import _holder_process_tree_has_pytest
    except ImportError:
        pass
    else:
        if _holder_process_tree_has_pytest(row.pid):
            parallel_stuck = _parallel_node_stuck_reason(row)
            if parallel_stuck is not None:
                return parallel_stuck
            return None
    chrome_row = LiveChromeE2ERow(
        pid=row.pid,
        elapsed_sec=row.elapsed_sec,
        command=row.test_id,
        test_id=row.test_id,
        state=row.state,
    )
    reason = _hung_reason_for_row(
        chrome_row,
        admit_elapsed_sec=row.admit_elapsed_sec,
    )
    if reason is not None:
        return reason
    parallel_stuck = _parallel_node_stuck_reason(row)
    if parallel_stuck is not None:
        return parallel_stuck
    wall = str(row.wall_phase or row.phase or "").strip().lower()
    if wall == "bootstrap":
        from e2e_session_snapshot import (  # noqa: PLC0415
            phase_elapsed_from_snapshot,
            resolve_session_snapshot,
        )

        snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
        if _process_has_signoff_env(row.pid):
            from dev_gate_contract import (
                signoff_effective_bootstrap_wall_sec,
            )  # noqa: PLC0415

            bootstrap_cap = signoff_effective_bootstrap_wall_sec()
            bootstrap_elapsed = (
                phase_elapsed_from_snapshot(snapshot)
                if snapshot is not None
                else row.node_elapsed_sec
            )
        elif snapshot is not None:
            from dev_gate_contract import (  # noqa: PLC0415
                dev_bootstrap_wall_cap_for_hung_reap,
            )

            lane = (
                str(snapshot.get("lane") or row.lane or "RESOURCE_WRITE")
                .strip()
                .upper()
                or "RESOURCE_WRITE"
            )
            shpoib = snapshot.get("shpoib") is True or bool(row.shpoib)
            bootstrap_cap = dev_bootstrap_wall_cap_for_hung_reap(
                lane=lane,
                shpoib=shpoib,
            )
            snapshot_cap = snapshot.get("phaseCapSec")
            if isinstance(snapshot_cap, (int, float)) and float(snapshot_cap) > 0:
                bootstrap_cap = max(bootstrap_cap, float(snapshot_cap))
            bootstrap_elapsed = phase_elapsed_from_snapshot(snapshot)
        else:
            from dev_gate_contract import (
                dev_bootstrap_wall_cap_for_hung_reap,
            )  # noqa: PLC0415

            lane = str(row.lane or "RESOURCE_WRITE").strip().upper() or "RESOURCE_WRITE"
            bootstrap_cap = dev_bootstrap_wall_cap_for_hung_reap(
                lane=lane,
                shpoib=bool(row.shpoib),
            )
            bootstrap_elapsed = row.node_elapsed_sec
        if bootstrap_elapsed is None:
            bootstrap_elapsed = row.node_elapsed_sec
        if bootstrap_elapsed is None:
            bootstrap_elapsed = row.elapsed_sec
        if float(bootstrap_elapsed) >= float(bootstrap_cap):
            return f"bootstrap_elapsed={int(bootstrap_elapsed)}s>={int(bootstrap_cap)}s"
    admit_semantic = _admit_semantic_node_stuck_reason(row)
    if admit_semantic is not None:
        return admit_semantic
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
    stall_cap = shpoib_parallel_stall_progress_sec(
        lane=str(snapshot.get("lane") or ""),
        workload=str(snapshot.get("workload") or ""),
    )
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
        if not row.owner_alive:
            print(
                f"E2E_OWNER_DEAD_LEASE_REAP: lease={row.lease_id[:8]} "
                f"owner_pid={row.owner_pid} linked_pytest={row.linked_pytest or 'none'} "
                "(do not stop other pytest)",
                file=sys.stderr,
                flush=True,
            )
            if expire_lease_watchdog(row.lease_id):
                reaped = True
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
    """Removed: m3-signoff maintenance gate deleted."""
    return False


def _desktop_soak_runner_active() -> bool:
    """Removed: m3-leg-soak maintenance script deleted."""
    return False


def _elapsed_sec_from_reason(reason: str, *, prefix: str) -> int | None:
    import re

    match = re.search(rf"{re.escape(prefix)}=(\d+)s", reason)
    if match is None:
        return None
    return int(match.group(1))


def _past_body_wall_cap(row: LiveE2ESessionRow, reason: str) -> bool:
    """True when hung reason exceeds per-process BODY wall SSOT."""
    from dev_gate_contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415

    cap = _body_wall_cap_for_pid(row.pid)
    if E2E_BODY_WALL_EXCEEDED_TOKEN in reason:
        body_elapsed = _elapsed_sec_from_reason(reason, prefix="body_elapsed")
        return body_elapsed is not None and body_elapsed >= cap
    if reason.startswith("process_elapsed="):
        elapsed = _elapsed_sec_from_reason(reason, prefix="process_elapsed")
        if elapsed is None:
            elapsed = int(row.elapsed_sec)
        return float(elapsed) >= cap
    return float(row.elapsed_sec) >= cap


def _desktop_soak_reap_immunity(row: LiveE2ESessionRow, reason: str) -> bool:
    """Skip false-positive hung-reap on desktop soak pytest (HITL/mux waits > NODE_STUCK)."""
    if not _process_has_desktop_soak_env(row.pid):
        return False
    if reason.startswith(("bootstrap_elapsed=", "admit_elapsed=")):
        return False
    from dev_gate_contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415

    if E2E_BODY_WALL_EXCEEDED_TOKEN in reason:
        if _process_has_signoff_env(row.pid):
            return not _past_body_wall_cap(row, reason)
        body_elapsed = _elapsed_sec_from_reason(reason, prefix="body_elapsed")
        from dev_gate_contract import LIVE_AGENT_BODY_WALL_CLOCK_SEC  # noqa: PLC0415

        if body_elapsed is not None and body_elapsed >= float(
            LIVE_AGENT_BODY_WALL_CLOCK_SEC
        ):
            return False
        return not _past_body_wall_cap(row, reason)
    if reason.startswith("E2E_NODE_STUCK"):
        return True
    if reason.startswith("progress_stale="):
        return True
    if reason.startswith("process_elapsed=") and row.phase == "body":
        if not _process_has_signoff_env(row.pid):
            from dev_gate_contract import (
                LIVE_AGENT_BODY_WALL_CLOCK_SEC,
            )  # noqa: PLC0415

            elapsed = _elapsed_sec_from_reason(reason, prefix="process_elapsed")
            if elapsed is None:
                elapsed = int(row.elapsed_sec)
            if float(elapsed) >= float(LIVE_AGENT_BODY_WALL_CLOCK_SEC):
                return False
        return not _past_body_wall_cap(row, reason)
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
    from dev_gate_contract import E2E_ADMIT_NODE_STUCK_TOKEN  # noqa: PLC0415

    if reason.startswith(E2E_ADMIT_NODE_STUCK_TOKEN):
        return False
    if reason.startswith("E2E_NODE_STUCK"):
        return False
    if _parallel_node_stuck_reason(row) is not None:
        return False
    from dev_gate_contract import E2E_BODY_WALL_EXCEEDED_TOKEN  # noqa: PLC0415

    if E2E_BODY_WALL_EXCEEDED_TOKEN in reason:
        return not _past_body_wall_cap(row, reason)
    if _session_row_is_healthy_body(row):
        return True
    if reason.startswith("process_elapsed="):
        if row.phase != "body":
            return False
        if _past_body_wall_cap(row, reason):
            return False
        try:
            from e2e_session_snapshot import resolve_session_snapshot  # noqa: PLC0415
        except ImportError:
            return False
        return resolve_session_snapshot(pid=row.pid, test_id=row.test_id) is not None
    return False


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
        from dev_gate_contract import (  # noqa: PLC0415
            E2E_ADMIT_NODE_STUCK_TOKEN,
            E2E_BODY_WALL_EXCEEDED_TOKEN,
        )

        force_kill = (
            "E2E_ADMIT_STALL" in reason
            or reason.startswith(E2E_ADMIT_NODE_STUCK_TOKEN)
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


def maybe_reap_stale_empty_mux_contexts(*, min_stale: int = 3) -> bool:
    """Reap idle mux shim contexts with zero owned pages (P0-A transport hygiene)."""
    if not _coordinator_reap_authorized():
        return False
    try:
        from mux_load import (
            read_mux_status,
            reap_idle_empty_mux_contexts,
            stale_empty_mux_context_count,
        )
    except ImportError:
        return False
    status = read_mux_status(force=True)
    stale = stale_empty_mux_context_count(status)
    if stale < max(1, int(min_stale)):
        return False
    result = reap_idle_empty_mux_contexts()
    reaped = (
        int(result.get("reaped", 0)) if isinstance(result.get("reaped"), int) else 0
    )
    if reaped <= 0:
        return False
    print(
        f"E2E_MUX_REAP_IDLE: stale_empty={stale} reaped={reaped} "
        f"remaining={result.get('remaining')} (do not stop other pytest)",
        file=sys.stderr,
        flush=True,
    )
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


_EPOCH_DRIFT_REAPER_BUDGET_SEC = 180.0


def _epoch_drift_reaper_budget_sec(row: LiveE2ESessionRow) -> float:
    """Phase-aware epoch-drift reap cap — must match ADMIT/BOOTSTRAP lifecycle SSOT.

    tools_panel log-7 @ ~240s: ADMIT_STACK_HEAL_WAIT + stack heal exceeded the legacy
    180s process_elapsed cap while epoch_match=no; SIGTERM during shared UI recover.
    """
    phase = str(row.wall_phase or row.phase or "").strip().lower()
    from dev_gate_contract import (  # noqa: PLC0415
        admit_wall_clock_sec,
        dev_bootstrap_wall_cap_for_hung_reap,
    )

    if phase == "admit":
        return float(admit_wall_clock_sec())
    if phase == "bootstrap":
        lane = str(row.lane or "LIVE_AGENT").strip().upper() or "LIVE_AGENT"
        return dev_bootstrap_wall_cap_for_hung_reap(lane=lane, shpoib=bool(row.shpoib))
    return _EPOCH_DRIFT_REAPER_BUDGET_SEC


def _epoch_drift_elapsed_sec(row: LiveE2ESessionRow) -> float:
    phase = str(row.wall_phase or row.phase or "").strip().lower()
    if phase == "admit" and row.admit_elapsed_sec is not None:
        return float(row.admit_elapsed_sec)
    if phase == "bootstrap":
        from e2e_session_snapshot import (  # noqa: PLC0415
            phase_elapsed_from_snapshot,
            resolve_session_snapshot,
        )

        snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
        if snapshot is not None:
            phase_elapsed = phase_elapsed_from_snapshot(snapshot)
            if phase_elapsed is not None:
                return float(phase_elapsed)
    return float(row.elapsed_sec)


def maybe_reap_epoch_drift_stale_sessions() -> bool:
    """Layer-3 safety net: reap sessions stuck in ADMIT/BOOTSTRAP with epoch_match=no.

    When epoch drift persists and Layers 1+2 haven't fully released all leases
    (e.g. tests started before the guard was deployed), this coordinator-level
    reaper forcibly releases their leases to allow system restart.
    Budget follows admit_wall_clock_sec / dev_bootstrap_wall_cap_for_hung_reap (P0-E).
    """
    if not _coordinator_reap_authorized():
        return False

    try:
        from e2e_api_verify import resolve_e2e_api_context
    except ImportError:
        return False

    ctx = resolve_e2e_api_context(retry_after_apply=False)
    if ctx.epoch_match or not ctx.blocked:
        return False

    reaped = False
    for row in list_live_e2e_sessions():
        if row.phase not in ("bootstrap", "admit"):
            continue
        # R279: M3 signoff legs queue through drift — do not coordinator-reap at 180s.
        if _process_has_signoff_env(row.pid):
            continue
        budget_sec = _epoch_drift_reaper_budget_sec(row)
        elapsed_sec = _epoch_drift_elapsed_sec(row)
        if elapsed_sec < budget_sec:
            continue
        print(
            f"E2E_EPOCH_DRIFT_REAP: pid={row.pid} test={row.test_id} "
            f"phase={row.phase} elapsed={elapsed_sec:.0f}s cap={budget_sec:.0f}s "
            f"(epoch_match=no, blocked={ctx.blocked_reason!r}) "
            "(releasing lease to allow system restart)",
            file=sys.stderr,
            flush=True,
        )
        if _terminate_hung_pytest(row.pid, admit_stall=False):
            reaped = True
            time.sleep(0.5)

    if reaped:
        wave_bin = _monorepo_root() / "myrm-agent" / "scripts" / "dev" / "wave.sh"
        subprocess.run(
            ["bash", str(wave_bin), "reap"],
            check=False,
            env=os.environ.copy(),
        )
    return reaped


def _backend_recorded_pids(state_dir: Path) -> set[int]:
    """Read backend.pid + backend-process.json to find recorded shared-backend pids."""
    pids: set[int] = set()
    pid_file = state_dir / "backend.pid"
    if pid_file.is_file():
        try:
            raw = pid_file.read_text(encoding="utf-8").strip()
            if raw.isdigit():
                pids.add(int(raw))
        except OSError:
            pass
    identity_file = state_dir / "backend-process.json"
    if identity_file.is_file():
        try:
            payload = json.loads(identity_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = None
        if isinstance(payload, dict):
            pid = payload.get("pid")
            if isinstance(pid, int):
                pids.add(pid)
    return pids


def _pid_listening_on(pid: int, port: int) -> bool:
    """True when pid currently LISTENs on 127.0.0.1:port (lsof is port-truth SSOT)."""
    try:
        proc = subprocess.run(
            ["lsof", "-nP", "-iTCP:{port}".format(port=port), "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if proc is None or proc.returncode != 0:
        return False
    return str(pid) in {
        line.strip() for line in proc.stdout.splitlines() if line.strip()
    }


def _pid_is_shared_backend(pid: int, shared_state_dir: Path) -> bool:
    """A recorded backend belongs to the shared stack only when its state dir matches."""
    environ = _process_ps_environ(pid)
    return str(shared_state_dir) in environ


def maybe_reap_orphan_shared_backends(
    *,
    min_age_sec: int = 120,
    state_dir: Path | None = None,
) -> bool:
    """§26.28-A: reap orphaned shared-backend run.py that no longer serve their port.

    Root cause: high load + repeated drift applies left stale `run.py` processes
    (PPID=1, no session lease, either never bound :8080 or lost it after a failed
    restart). They write the shared backend.log, hold sqlite shm, and cause
    `STACK_FAIL: private backend port :8080 still busy` on the next restart —
    the observed "backend repeatedly crashing / BLOCKED" loop.

    Safety invariants (port-truth SSOT, matching backend_bg.sh):
    - Only consider pids recorded in {state}/backend.pid or backend-process.json.
    - Only when that pid's env declares the shared state dir (never a private runtime).
    - Never kill the live :8080 LISTEN owner (that is the authoritative backend).
    - Skip pids referenced by any live e2e session (owner_pid).
    """
    if not _coordinator_reap_authorized():
        return False
    if state_dir is None:
        from dev_state_paths import dev_state_dir  # noqa: PLC0415

        state_dir = Path(dev_state_dir())
    if not state_dir.is_dir():
        return False
    recorded = _backend_recorded_pids(state_dir)
    if not recorded:
        return False
    live_owner = _pid_listening_on(0, 8080)
    if live_owner:
        recorded.discard(live_owner)
    # Protect pids owned by live wave leases or live pytest sessions.
    protected_pids: set[int] = set()
    try:
        import e2e_lease_liveness  # noqa: PLC0415
        import e2e_session_registry  # noqa: PLC0415

        for row in e2e_lease_liveness.build_lease_liveness(
            e2e_lease_liveness.load_wave_snapshot()
        ):
            if row.owner_pid is not None:
                protected_pids.add(row.owner_pid)
        for row in e2e_session_registry.list_live_e2e_sessions():
            protected_pids.add(row.pid)
    except (ImportError, OSError):
        pass
    reaped = False
    for pid in sorted(recorded):
        if not _process_alive(pid):
            continue
        if pid in protected_pids:
            continue
        if not _pid_is_shared_backend(pid, state_dir):
            continue
        if _pid_listening_on(pid, 8080):
            continue
        try:
            start = time.time()
            info = subprocess.run(
                ["ps", "-o", "lstart=", "-p", str(pid)],
                capture_output=True,
                text=True,
                check=False,
                timeout=5,
            )
            # Best-effort age gate: skip recent starts that may still be binding.
            if info.returncode == 0:
                try:
                    started = time.mktime(
                        time.strptime(info.stdout.strip(), "%a %b %d %H:%M:%S %Y")
                    )
                except ValueError:
                    started = None
                if started is not None and (time.time() - started) < min_age_sec:
                    continue
        except (OSError, subprocess.TimeoutExpired):
            pass
        print(
            f"E2E_ORPHAN_SHARED_BACKEND_REAP: pid={pid} recorded but not serving "
            f":8080 — terminating orphaned shared backend (do not stop other pytest)",
            file=sys.stderr,
            flush=True,
        )
        if _terminate_hung_pytest(pid, admit_stall=False):
            reaped = True
            time.sleep(0.3)
    return reaped
