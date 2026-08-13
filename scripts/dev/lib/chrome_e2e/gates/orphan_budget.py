"""Orphan blank tab budget invariant (P0-UX-3 · TAB-5).

Invariant: about:blank page count must not exceed active page lease ceiling + slack.
A violation persisting longer than ORPHAN_BUDGET_FAIL_SEC triggers fail-fast.
"""

from __future__ import annotations

import os
import time
from typing import TypedDict

from dev_gate.contract import (
    E2E_ORPHAN_BUDGET_EXCEEDED_TOKEN,
    ORPHAN_BUDGET_FAIL_SEC,
    ORPHAN_BUDGET_SLACK,
)


class OrphanBudgetEvaluation(TypedDict):
    ok: bool
    blank_count: int
    lease_ceiling: int
    violation_sec: float
    detail: str


_violation_started_mono: float | None = None


def _chrome_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 9333


def count_blank_cdp_pages(*, cdp_port: int | None = None) -> int:
    return count_stray_blank_cdp_pages(cdp_port=cdp_port)


def count_stray_blank_cdp_pages(*, cdp_port: int | None = None) -> int:
    from e2e_core.browser_tab_hygiene import (  # noqa: PLC0415
        _is_blankish_url,
        _list_cdp_pages,
        _protected_target_ids,
    )

    port = cdp_port if cdp_port is not None else _chrome_port()
    pages = _list_cdp_pages(port)
    protected = _protected_target_ids()
    if protected is None:
        return sum(1 for page in pages if _is_blankish_url(page.get("url")))
    stray = 0
    for page in pages:
        if not _is_blankish_url(page.get("url")):
            continue
        target_id = page.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            continue
        if target_id.strip() in protected:
            continue
        stray += 1
    return stray


def active_page_lease_ceiling() -> int:
    from e2e_core.lease_liveness import (  # noqa: PLC0415
        load_wave_snapshot_observation,
        wave_lease_counts,
    )
    from e2e_core.parallel_status import (  # noqa: PLC0415
        resolve_parallel_runtime_snapshot,
        safe_active_test_count,
    )

    parallel, _ = resolve_parallel_runtime_snapshot()
    active_tests = safe_active_test_count(parallel)
    wave_snapshot = load_wave_snapshot_observation()
    counts = wave_lease_counts(wave_snapshot)
    effective_leases = max(0, counts.effective_total)
    burst_lanes = 0
    for key in ("MYRM_E2E_PHASE_C_BURST_LANES", "MYRM_E2E_PARALLEL_ACTIVE_LEASES"):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            burst_lanes = max(burst_lanes, int(raw))
    return max(active_tests, effective_leases, burst_lanes, 1)


def evaluate_orphan_budget(*, cdp_port: int | None = None) -> OrphanBudgetEvaluation:
    global _violation_started_mono

    blank_count = count_stray_blank_cdp_pages(cdp_port=cdp_port)
    ceiling = active_page_lease_ceiling() + ORPHAN_BUDGET_SLACK
    if blank_count <= ceiling:
        _violation_started_mono = None
        return {
            "ok": True,
            "blank_count": blank_count,
            "lease_ceiling": ceiling,
            "violation_sec": 0.0,
            "detail": f"blank={blank_count} ceiling={ceiling}",
        }

    now = time.monotonic()
    if _violation_started_mono is None:
        _violation_started_mono = now
    violation_sec = now - _violation_started_mono
    return {
        "ok": False,
        "blank_count": blank_count,
        "lease_ceiling": ceiling,
        "violation_sec": violation_sec,
        "detail": (
            f"blank={blank_count} exceeds ceiling={ceiling} "
            f"for {violation_sec:.1f}s"
        ),
    }


def assert_orphan_budget_invariant(*, cdp_port: int | None = None) -> None:
    evaluation = evaluate_orphan_budget(cdp_port=cdp_port)
    if evaluation["ok"]:
        return
    if evaluation["violation_sec"] >= ORPHAN_BUDGET_FAIL_SEC:
        raise RuntimeError(
            f"{E2E_ORPHAN_BUDGET_EXCEEDED_TOKEN}: {evaluation['detail']}"
        )


def reset_orphan_budget_violation_clock() -> None:
    """Test helper: clear violation persistence."""
    global _violation_started_mono
    _violation_started_mono = None
