"""Chrome E2E launch preflight gate (R166 UPAP).

[INPUT]
- e2e_api_verify.resolve_e2e_api_context / _compute_next_action (POS: Agent SSOT)
- e2e_lease_liveness.wave_lease_counts (POS: effective cap headroom)

[OUTPUT]
- chrome_e2e_launch_denial_reason() -> str | None
- assert_chrome_e2e_launch_allowed() -> None (exit 2 on deny)

[POS]
test.sh fail-closed gate before session dedupe when cluster NEXT_ACTION=FAIL_FAST.
"""

from __future__ import annotations

import os
import sys


def chrome_e2e_launch_denial_reason() -> str | None:
    """Return human+machine denial line when a new chrome_e2e launch must abort."""
    if os.environ.get("MYRM_E2E_LAUNCH_FORCE", "").strip() == "1":
        return None
    from e2e_api_verify import (  # noqa: PLC0415
        _cap_headroom_fields,
        _compute_next_action,
        _load_parallel_runtime_snapshot,
        _mux_context_fields,
        resolve_e2e_api_context,
    )
    from e2e_lease_liveness import load_wave_snapshot, wave_lease_counts  # noqa: PLC0415

    ctx = resolve_e2e_api_context()
    mux_fields = _mux_context_fields()
    parallel_snapshot, _lines = _load_parallel_runtime_snapshot()
    counts = wave_lease_counts(load_wave_snapshot())
    active_tests_raw = parallel_snapshot.get("active_tests")
    active_tests = (
        [item for item in active_tests_raw if isinstance(item, dict)]
        if isinstance(active_tests_raw, list)
        else []
    )
    active_test_count = int(parallel_snapshot.get("active_test_count", 0))
    headroom = _cap_headroom_fields(
        lease_counts=counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
    )
    next_action = _compute_next_action(
        ctx,
        headroom=headroom,
        active_tests=active_tests,
        mux_fields=mux_fields,
    )
    if next_action != "FAIL_FAST":
        return None
    return (
        "E2E_LAUNCH_DENIED: NEXT_ACTION=FAIL_FAST; "
        "cluster has hung chrome_e2e peer — run ./myrm e2e-context; "
        "maintainer override MYRM_E2E_LAUNCH_FORCE=1 "
        "(do not stop other pytest)"
    )


def assert_chrome_e2e_launch_allowed() -> None:
    """Exit 2 when launch preflight denies a new chrome_e2e session."""
    reason = chrome_e2e_launch_denial_reason()
    if reason is None:
        return
    print(reason, file=sys.stderr, flush=True)
    raise SystemExit(2)
