"""Idle-safe prune of self-owned blank E2E Chrome tabs (maintainer UX).

[INPUT]
- e2e_parallel_status.load_parallel_runtime_snapshot (active pytest peers)
- e2e_lease_liveness.wave_lease_counts (wave lease observation)
- browser_orchestrator.prune_self_owned_blanks (exact ownership close)

[OUTPUT]
- idle_prune_self_owned_blanks_if_safe() → result dict for logs/CLI

[POS]
Dev gate maintainer hygiene only. Never prune during active chrome_e2e BODY.
"""

from __future__ import annotations

import json
import os
from typing import TypedDict


class IdlePruneResult(TypedDict, total=False):
    ok: bool
    skipped: str
    active_tests: int
    wave_leases_effective: int
    infra_closed: int
    infra_failed: int
    orphan_closed: int
    orphan_failed: int
    detail: str


def _chrome_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 9333


def idle_prune_self_owned_blanks_if_safe(
    *,
    cdp_port: int | None = None,
    threshold: int = 5,
) -> IdlePruneResult:
    """Prune blank tabs only when no chrome_e2e peers and no effective wave leases."""
    from e2e_lease_liveness import (  # noqa: PLC0415
        load_wave_snapshot_observation,
        wave_lease_counts,
    )
    from e2e_parallel_status import (  # noqa: PLC0415
        load_parallel_runtime_snapshot,
        safe_active_test_count,
    )

    port = cdp_port if cdp_port is not None else _chrome_port()
    parallel, _ = load_parallel_runtime_snapshot()
    active = safe_active_test_count(parallel)
    if active > 0:
        return {
            "ok": False,
            "skipped": "active_tests",
            "active_tests": active,
            "detail": "parallel chrome_e2e active — refuse blank prune",
        }

    wave_snapshot = load_wave_snapshot_observation()
    counts = wave_lease_counts(wave_snapshot)
    effective_raw = counts.get("effective", counts.get("waveLeasesEffective", 0))
    try:
        effective = int(effective_raw or 0)
    except (TypeError, ValueError):
        effective = -1
    if effective < 0:
        return {
            "ok": False,
            "skipped": "wave_observability_unknown",
            "detail": "wave lease count unknown — refuse blank prune",
        }
    if effective > 0:
        return {
            "ok": False,
            "skipped": "wave_leases",
            "wave_leases_effective": effective,
            "detail": "active wave leases — refuse blank prune",
        }

    os.environ["MYRM_BROWSER_ORCHESTRATOR_PRUNE"] = "1"
    from browser_orchestrator import prune_self_owned_blanks  # noqa: PLC0415

    infra_closed, infra_failed, orphan_closed, orphan_failed = prune_self_owned_blanks(
        cdp_port=port,
        threshold=threshold,
    )
    return {
        "ok": True,
        "infra_closed": infra_closed,
        "infra_failed": infra_failed,
        "orphan_closed": orphan_closed,
        "orphan_failed": orphan_failed,
        "detail": "idle blank prune complete",
    }


def main() -> int:
    result = idle_prune_self_owned_blanks_if_safe()
    print(f"IDLE_TAB_PRUNE: {json.dumps(result, sort_keys=True)}")
    if result.get("ok"):
        return 0
    skipped = str(result.get("skipped", ""))
    if skipped in {"active_tests", "wave_leases", "wave_observability_unknown"}:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
