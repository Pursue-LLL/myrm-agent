"""Signoff wave quiesce: reap dead-owner leases without force-closing live sessions."""

from __future__ import annotations

import os
import sys
import time
from typing import TypedDict


class QuiesceResult(TypedDict):
    ok: bool
    activeAlive: int
    activeDeadOwner: int
    waveStatus: str | None
    waitedSec: int
    message: str


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _ensure_wave_import_path() -> None:
    root = os.environ.get("MONOREPO_ROOT", "").strip()
    if not root:
        raise RuntimeError("MONOREPO_ROOT is required for signoff wave quiesce")
    agent_dev = os.path.join(root, "myrm-agent", "scripts", "dev")
    if agent_dev not in sys.path:
        sys.path.insert(0, agent_dev)


def classify_active_leases(
    active_leases: list[object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    from wave_orchestrator.lease_state import owner_bashpid_from_agent_id

    alive_owner: list[dict[str, object]] = []
    dead_owner: list[dict[str, object]] = []
    for item in active_leases:
        if not isinstance(item, dict):
            continue
        lease = item
        agent_id = str(lease.get("agentId", ""))
        owner_pid = owner_bashpid_from_agent_id(agent_id)
        if owner_pid is not None and not _process_alive(owner_pid):
            dead_owner.append(lease)
        else:
            alive_owner.append(lease)
    return alive_owner, dead_owner


def run_signoff_wave_quiesce(
    *,
    max_wait_sec: int | None = None,
    poll_sec: int | None = None,
) -> QuiesceResult:
    """Reap abandoned leases; wait only for dead-owner ghosts (parallel-friendly)."""
    _ensure_wave_import_path()
    from dev_gate_contract import (  # noqa: WPS433
        SIGNOFF_WAVE_QUIESCE_POLL_SEC,
        SIGNOFF_WAVE_QUIESCE_WAIT_SEC,
    )
    from wave_orchestrator.core import reap, wave_status

    max_wait = (
        SIGNOFF_WAVE_QUIESCE_WAIT_SEC if max_wait_sec is None else max_wait_sec
    )
    poll = SIGNOFF_WAVE_QUIESCE_POLL_SEC if poll_sec is None else poll_sec
    start = time.monotonic()
    deadline = start + max_wait

    while True:
        reap()
        status = wave_status()
        wave = status.get("wave")
        wave_status_str: str | None = None
        if isinstance(wave, dict):
            raw_status = wave.get("status")
            if isinstance(raw_status, str):
                wave_status_str = raw_status

        active_raw = status.get("activeLeases")
        active_list = active_raw if isinstance(active_raw, list) else []
        alive_owner, dead_owner = classify_active_leases(active_list)
        waited_sec = int(time.monotonic() - start)

        print(
            "SIGNOFF_WAVE_QUIESCE: "
            f"wave={wave_status_str or 'none'} "
            f"alive={len(alive_owner)} "
            f"dead_owner_stuck={len(dead_owner)} "
            f"waited={waited_sec}s",
            file=sys.stderr,
            flush=True,
        )

        if not dead_owner:
            return QuiesceResult(
                ok=True,
                activeAlive=len(alive_owner),
                activeDeadOwner=0,
                waveStatus=wave_status_str,
                waitedSec=waited_sec,
                message="quiesced",
            )

        if time.monotonic() >= deadline:
            return QuiesceResult(
                ok=False,
                activeAlive=len(alive_owner),
                activeDeadOwner=len(dead_owner),
                waveStatus=wave_status_str,
                waitedSec=waited_sec,
                message="dead-owner leases not reaped before timeout",
            )

        time.sleep(poll)


def main() -> int:
    os.environ.setdefault("MONOREPO_ROOT", "")
    lib_dir = os.path.dirname(os.path.abspath(__file__))
    if lib_dir not in sys.path:
        sys.path.insert(0, lib_dir)
    result = run_signoff_wave_quiesce()
    if result["ok"]:
        print(
            "SIGNOFF_WAVE_QUIESCE_OK "
            f"alive={result['activeAlive']} waited={result['waitedSec']}s"
        )
        return 0
    print(
        f"SIGNOFF_WAVE_QUIESCE_FAIL: {result['message']} "
        f"dead_owner={result['activeDeadOwner']} alive={result['activeAlive']}",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
