"""Exact-target abort compensation for new_page create transactions (P0-UX-1b).

[INPUT]
- CDP HTTP close for exact targetId only (via infra_browser_registry)

[OUTPUT]
- close_exact_unpublished_targets() → (closed, failed)

[POS]
Dev Gate client layer. Never URL/blank heuristic — exact ownership only.
"""

from __future__ import annotations

import os


def close_exact_unpublished_targets(
    target_ids: set[str],
    *,
    keep: frozenset[str] = frozenset(),
    cdp_port: int | None = None,
) -> tuple[int, int]:
    """Close pending exact targetIds owned by this transaction; skip protected/keep."""
    if not target_ids:
        return 0, 0
    port_raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        port = cdp_port if cdp_port is not None else max(int(port_raw), 1)
    except ValueError:
        port = 9333

    from e2e_core.browser_tab_hygiene import _protected_target_ids  # noqa: PLC0415
    from e2e_core.infra_browser_registry import close_exact_target  # noqa: PLC0415

    protected = _protected_target_ids()
    if protected is None:
        return 0, 0

    closed = 0
    failed = 0
    for target_id in list(target_ids):
        tid = target_id.strip()
        if not tid or tid in keep:
            continue
        if tid in protected:
            target_ids.discard(tid)
            continue
        if close_exact_target(port, tid):
            closed += 1
            target_ids.discard(tid)
        else:
            failed += 1
    return closed, failed
