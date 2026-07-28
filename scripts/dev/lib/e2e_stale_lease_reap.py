"""Reap excess wave leases when holder pytest processes are gone (R58 hygiene).

[INPUT]
- stack_mutation_policy.wave_active_lease_count (POS: active wave lease tally)
- e2e_live_chrome_pytest_scan list (canonical inner pytest pid)
- e2e_session_snapshot body_elapsed / progress stall (R62 Phase B)

[OUTPUT]
- maybe_reap_excess_wave_leases: run wave reap when leases exceed live tests + slack
- maybe_reap_hung_chrome_e2e_pytest: SIGINT hung BODY tests + wave reap

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

from e2e_live_chrome_pytest_scan import (
    LiveChromeE2ERow,
    list_live_chrome_e2e_pytest_rows,
)


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
    from dev_gate_contract import (  # noqa: PLC0415
        LIVE_AGENT_PYTEST_WALL_CAP_SEC,
        LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
        STALL_PROGRESS_SEC,
    )
    from transport_supervisor import live_agent_pytest_wall_cap_sec  # noqa: PLC0415
    from e2e_session_snapshot import (  # noqa: PLC0415
        body_elapsed_from_snapshot,
        progress_stale_sec,
        resolve_session_snapshot,
    )

    snapshot = resolve_session_snapshot(pid=row.pid, test_id=row.test_id)
    if snapshot is not None:
        body_elapsed = body_elapsed_from_snapshot(snapshot)
        if body_elapsed is not None and body_elapsed >= float(
            LIVE_SINGLE_TEST_WALL_CLOCK_SEC
        ):
            return (
                f"body_elapsed={int(body_elapsed)}s>={LIVE_SINGLE_TEST_WALL_CLOCK_SEC}s"
            )
        stale = progress_stale_sec(snapshot)
        if (
            body_elapsed is not None
            and body_elapsed >= 30.0
            and stale is not None
            and stale >= float(STALL_PROGRESS_SEC)
        ):
            return f"progress_stale={int(stale)}s>={STALL_PROGRESS_SEC}s"
    if row.elapsed_sec >= float(live_agent_pytest_wall_cap_sec()):
        return (
            f"process_elapsed={int(row.elapsed_sec)}s>="
            f"{live_agent_pytest_wall_cap_sec()}s"
        )
    return None


def maybe_reap_hung_chrome_e2e_pytest(*, skip_pid: int | None = None) -> bool:
    """SIGINT pytest processes exceeding BODY budget or progress stall; then wave reap."""
    reaped = False
    for row in list_live_chrome_e2e_pytest_rows():
        if skip_pid is not None and row.pid == skip_pid:
            continue
        reason = _hung_reason_for_row(row)
        if reason is None:
            continue
        print(
            f"E2E_HUNG_PYTEST_REAP: pid={row.pid} test={row.test_id} reason={reason} "
            "(do not stop other pytest)",
            file=sys.stderr,
            flush=True,
        )
        try:
            os.kill(row.pid, signal.SIGINT)
        except OSError:
            continue
        reaped = True
        time.sleep(0.5)
    if not reaped:
        return False
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
    active_tests = len(list_live_chrome_e2e_pytest_rows())
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
