"""Observed cleanup seal for Dev Gate coordinator sessions (P0-A)."""

from __future__ import annotations

import json
from pathlib import Path


def _wave_state_path() -> Path:
    from wave_state_paths import resolve_wave_state_file

    return resolve_wave_state_file()


def lease_released(lease_id: str) -> bool:
    """True when the lease is absent or no longer active in wave state."""
    token = lease_id.strip()
    if not token:
        return True
    try:
        payload = json.loads(_wave_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    leases = payload.get("leases") if isinstance(payload, dict) else None
    if not isinstance(leases, list):
        return True
    for item in leases:
        if not isinstance(item, dict):
            continue
        if str(item.get("leaseId", "")).strip() != token:
            continue
        return str(item.get("status", "")).strip().lower() != "active"
    return True


def observe_cleanup_seal(
    *,
    released_lease_id: str,
    owned_page_ids: tuple[str, ...],
    owned_context_id: str,
) -> tuple[bool, bool]:
    """Return (ledger_cleaned, sealed).

    sealed is True only when lease release is observed and no browser ownership remains
    registered on the session (pages/context must be cleared before seal).
    """
    ledger_cleaned = lease_released(released_lease_id)
    ownership_cleared = not owned_page_ids and not owned_context_id.strip()
    sealed = ledger_cleaned and ownership_cleared
    return ledger_cleaned, sealed
