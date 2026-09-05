"""Observed cleanup seal for Dev Gate coordinator sessions.

[INPUT]
wave_state_paths (POS: wave-orchestrator.json 路径 SSOT)
browser_tab_hygiene (POS: CDP tab 计数报告)

[OUTPUT]
observe_cleanup_seal(): (ledger_cleaned, sealed) — 验证 lease release + CDP targets absent + ownership cleared

[POS]
物理资源签收层。cleanup 只有经 CDP targets absent + lease released 实证才返回 sealed=True，
阻止 synthetic receipt 产生假绿。
"""

from __future__ import annotations

import json
import time
from pathlib import Path


def _wave_state_path() -> Path:
    from e2e_core.wave_state_paths import resolve_wave_state_file

    return resolve_wave_state_file()


def collect_cdp_target_ids() -> frozenset[str] | None:
    """Live CDP page target ids; None when /json/list is unreadable (fail-closed)."""
    from e2e_core.browser_tab_hygiene import _chrome_port, _count_cdp_targets, _list_cdp_pages

    port = _chrome_port()
    if _count_cdp_targets(port) < 0:
        return None
    target_ids: set[str] = set()
    for page in _list_cdp_pages(port):
        target_id = page.get("id")
        if isinstance(target_id, str) and target_id.strip():
            target_ids.add(target_id.strip())
    return frozenset(target_ids)


def lease_bound_target_ids(lease_id: str) -> tuple[str, ...]:
    """Return CDP target ids bound to a wave lease (empty when lease unbound)."""
    token = lease_id.strip()
    if not token:
        return ()
    try:
        payload = json.loads(_wave_state_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    leases = payload.get("leases") if isinstance(payload, dict) else None
    if not isinstance(leases, list):
        return ()
    targets: list[str] = []
    for item in leases:
        if not isinstance(item, dict):
            continue
        if str(item.get("leaseId", "")).strip() != token:
            continue
        target_id = item.get("targetId")
        if isinstance(target_id, str) and target_id.strip():
            targets.append(target_id.strip())
    return tuple(targets)


def physical_targets_absent(*, lease_id: str) -> bool | None:
    """True when lease-bound CDP targets are absent; None when CDP snapshot unreadable."""
    bound = lease_bound_target_ids(lease_id)
    if not bound:
        # A non-empty lease with no recorded target still needs a positive CDP
        # observability sample. Returning True without probing would allow a
        # stale/malformed wave state file to manufacture a cleanup seal.
        if not lease_id.strip():
            return True
        return True if collect_cdp_target_ids() is not None else None
    live = collect_cdp_target_ids()
    if live is None:
        return None
    return not any(target_id in live for target_id in bound)


def poll_physical_targets_absent(
    *,
    lease_id: str,
    timeout_sec: float = 15.0,
    poll_sec: float = 0.5,
) -> bool | None:
    """Poll until lease-bound CDP targets disappear or timeout."""
    deadline = time.monotonic() + max(0.0, timeout_sec)
    last: bool | None = None
    while time.monotonic() <= deadline:
        last = physical_targets_absent(lease_id=lease_id)
        if last is True:
            return True
        time.sleep(max(0.05, poll_sec))
    return last


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

    sealed is True only when lease release is observed, coordinator ownership is cleared,
    and any lease-bound CDP targets are physically absent (fail-closed when CDP unreadable).
    """
    ledger_cleaned = lease_released(released_lease_id)
    ownership_cleared = not owned_page_ids and not owned_context_id.strip()
    physical_released = physical_targets_absent(lease_id=released_lease_id)
    sealed = ledger_cleaned and ownership_cleared and physical_released is True
    return ledger_cleaned, sealed
