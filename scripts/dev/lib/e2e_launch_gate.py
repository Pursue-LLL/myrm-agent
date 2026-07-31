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
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return None
    if os.environ.get("MYRM_E2E_SIGNOFF_CLARIFY_POOL", "").strip() == "1":
        return None
    from e2e_readiness import launch_denial_line, resolve_chrome_e2e_readiness  # noqa: PLC0415

    verdict = resolve_chrome_e2e_readiness()
    return launch_denial_line(verdict)


def assert_chrome_e2e_launch_allowed() -> None:
    """Exit 2 when launch preflight denies a new chrome_e2e session."""
    reason = chrome_e2e_launch_denial_reason()
    if reason is None:
        return
    print(reason, file=sys.stderr, flush=True)
    raise SystemExit(2)
