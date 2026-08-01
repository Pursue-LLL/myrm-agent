"""Fail-closed formal chrome E2E lease/runtimeId sync gate with in-place heal.

[INPUT]
- runtime_probe.py::_read_shared_hot_stack_runtime_id (POS: Dev infrastructure live stack probe)
- wave_state_paths.py::resolve_wave_state_file (POS: wave-orchestrator.json path SSOT bootstrap)
- wave_orchestrator.lease_state heal/reap helpers (POS: runtime drift heal under flock)

[OUTPUT]
- lease_runtime_matches_shared_hot(): bool + detail str (compare-only)
- sync_lease_runtime_with_shared_hot(): heal under wave lock then verify
- CLI exit 0 when MYRM_E2E_LEASE_ID.runtimeId matches shared-hot probe; exit 1 otherwise

[POS]
Dev Gate acquire gate. Ensures wave lease runtimeId matches live shared-hot stack before pytest starts.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from wave_state_paths import resolve_wave_state_file


def _dev_scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _ensure_wave_orchestrator_path() -> None:
    dev_scripts = str(_dev_scripts_dir())
    if dev_scripts not in sys.path:
        sys.path.insert(0, dev_scripts)


def _shared_hot_runtime_id() -> str:
    dev_lib = os.environ.get("MYRM_DEV_LIB", "").strip()
    if not dev_lib:
        raise RuntimeError("MYRM_DEV_LIB required")
    if dev_lib not in sys.path:
        sys.path.insert(0, dev_lib)
    from runtime_probe import _read_shared_hot_stack_runtime_id

    return _read_shared_hot_stack_runtime_id()


def _sync_max_attempts() -> int:
    raw = os.environ.get("MYRM_E2E_LEASE_SYNC_ATTEMPTS", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return 5
    leases_raw = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_LEASES", "").strip()
    if leases_raw.isdigit():
        leases = int(leases_raw)
        if leases >= 4:
            return 6
        if leases >= 2:
            return 4
    return 2


def lease_runtime_matches_shared_hot(*, lease_id: str) -> tuple[bool, str]:
    normalized_lease_id = lease_id.strip()
    if not normalized_lease_id:
        return False, "lease_id missing"

    state_path = resolve_wave_state_file()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"cannot read {state_path}: {exc}"

    try:
        live_runtime_id = _shared_hot_runtime_id().strip()
    except RuntimeError as exc:
        return False, str(exc)

    if not live_runtime_id:
        return False, "shared-hot probe returned empty runtimeId"

    lease_runtime_id = ""
    for item in payload.get("leases") or []:
        if not isinstance(item, dict):
            continue
        if (
            item.get("leaseId") == normalized_lease_id
            and item.get("status") == "active"
        ):
            lease_runtime_id = str(item.get("runtimeId", "")).strip()
            break

    if not lease_runtime_id:
        return False, f"active lease {normalized_lease_id} not found in {state_path}"

    if lease_runtime_id != live_runtime_id:
        return False, f"lease={lease_runtime_id} live={live_runtime_id}"

    return True, live_runtime_id


def _sync_lease_runtime_once(
    *, lease_id: str, live_runtime_id: str
) -> tuple[bool, str]:
    normalized_lease_id = lease_id.strip()
    state_path = resolve_wave_state_file()
    _ensure_wave_orchestrator_path()
    from wave_orchestrator.lease_state import (  # noqa: PLC0415
        find_active_lease,
        heal_open_wave_runtime_id_for_acquire,
        reap_abandoned_leases,
        reap_expired_leases,
        reap_runtime_drift,
    )
    from wave_orchestrator.store import run_locked  # noqa: PLC0415

    outcome: tuple[bool, str] = (False, "sync failed")

    def _edit(state: dict[str, object]) -> tuple[tuple[bool, str], bool]:
        nonlocal outcome
        changed = False
        if reap_abandoned_leases(state):  # type: ignore[arg-type]
            changed = True
        if reap_expired_leases(state, cleanup=False):  # type: ignore[arg-type]
            changed = True
        try:
            lease = find_active_lease(state, normalized_lease_id)  # type: ignore[arg-type]
        except RuntimeError:
            outcome = (
                False,
                f"active lease {normalized_lease_id} not found in {state_path}",
            )
            return outcome, changed

        lease_runtime = str(lease.get("runtimeId", "")).strip()
        agent_id = str(lease.get("agentId", "")).strip()
        if lease_runtime == live_runtime_id:
            outcome = (True, live_runtime_id)
            return outcome, changed

        if heal_open_wave_runtime_id_for_acquire(
            state,  # type: ignore[arg-type]
            live_runtime_id,
            agent_id,
        ):
            changed = True
        elif reap_runtime_drift(state, live_runtime_id):  # type: ignore[arg-type]
            changed = True
        else:
            wave = state.get("wave")
            if (
                isinstance(wave, dict)
                and str(wave.get("runtimeId", "")).strip() == live_runtime_id
            ):
                lease["runtimeId"] = live_runtime_id
                changed = True

        lease_runtime_after = str(lease.get("runtimeId", "")).strip()
        if lease_runtime_after == live_runtime_id:
            outcome = (True, live_runtime_id)
        else:
            outcome = (
                False,
                f"lease={lease_runtime_after} live={live_runtime_id}",
            )
        return outcome, changed

    run_locked(state_path, _edit)
    return outcome


def sync_lease_runtime_with_shared_hot(
    *,
    lease_id: str,
    max_attempts: int | None = None,
) -> tuple[bool, str]:
    normalized_lease_id = lease_id.strip()
    if not normalized_lease_id:
        return False, "lease_id missing"

    attempts = max_attempts if max_attempts is not None else _sync_max_attempts()
    last_detail = "sync failed"
    for attempt in range(1, max(1, attempts) + 1):
        try:
            live_runtime_id = _shared_hot_runtime_id().strip()
        except RuntimeError as exc:
            return False, str(exc)
        if not live_runtime_id:
            return False, "shared-hot probe returned empty runtimeId"

        ok, detail = _sync_lease_runtime_once(
            lease_id=normalized_lease_id,
            live_runtime_id=live_runtime_id,
        )
        if ok:
            return True, detail
        last_detail = detail
        if attempt < attempts:
            time.sleep(min(3 * attempt, 12))

    return False, last_detail


def main() -> int:
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    ok, detail = sync_lease_runtime_with_shared_hot(lease_id=lease_id)
    if ok:
        return 0
    print(f"E2E_LEASE_RUNTIME_SYNC_FAILED: {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
