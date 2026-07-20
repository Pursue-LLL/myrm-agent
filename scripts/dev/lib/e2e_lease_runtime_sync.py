"""Fail-closed formal chrome E2E lease/runtimeId sync gate.

[INPUT]
- runtime_probe.py::_read_shared_hot_stack_runtime_id (POS: Dev infrastructure live stack probe)
- wave_state_paths.py::resolve_wave_state_file (POS: wave-orchestrator.json path SSOT bootstrap)

[OUTPUT]
- lease_runtime_matches_shared_hot(): bool + detail str
- CLI exit 0 when MYRM_E2E_LEASE_ID.runtimeId matches shared-hot probe; exit 1 otherwise

[POS]
Dev Gate acquire gate. Ensures wave lease runtimeId matches live shared-hot stack before pytest starts.
"""

from __future__ import annotations

import json
import os
import sys

from wave_state_paths import resolve_wave_state_file


def _shared_hot_runtime_id() -> str:
    dev_lib = os.environ.get("MYRM_DEV_LIB", "").strip()
    if not dev_lib:
        raise RuntimeError("MYRM_DEV_LIB required")
    if dev_lib not in sys.path:
        sys.path.insert(0, dev_lib)
    from runtime_probe import _read_shared_hot_stack_runtime_id

    return _read_shared_hot_stack_runtime_id()


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
        if item.get("leaseId") == normalized_lease_id and item.get("status") == "active":
            lease_runtime_id = str(item.get("runtimeId", "")).strip()
            break

    if not lease_runtime_id:
        return False, f"active lease {normalized_lease_id} not found in {state_path}"

    if lease_runtime_id != live_runtime_id:
        return False, f"lease={lease_runtime_id} live={live_runtime_id}"

    return True, live_runtime_id


def main() -> int:
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    ok, detail = lease_runtime_matches_shared_hot(lease_id=lease_id)
    if ok:
        return 0
    print(f"E2E_LEASE_RUNTIME_SYNC_FAILED: {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
