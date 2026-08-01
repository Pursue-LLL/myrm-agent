"""First-party Browser Orchestrator snapshot (P0-B foundation).

Single persistent CDP ownership plane; max operation credits bound physical
browser concurrency instead of four independent MCP ownership processes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from enum import StrEnum
from typing import TypedDict

MAX_OPERATION_CREDITS = 4


class BrowserPlaneHealth(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class BrowserOrchestratorSnapshot(TypedDict, total=False):
    health: str
    operation_credits_max: int
    operation_credits_in_flight: int
    operation_credits_available: int
    mux_snapshot_available: bool
    mux_contexts: int
    wave_leases: int


def _mux_probe() -> tuple[bool, int, int]:
    try:
        from mux_load import read_mux_status, snapshot_mux_load

        status = read_mux_status()
        snap = snapshot_mux_load()
        return status is not None, int(snap.mux_contexts), int(snap.wave_leases)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return False, 0, 0


def _infer_health(*, mux_available: bool, in_flight: int) -> BrowserPlaneHealth:
    if not mux_available:
        return BrowserPlaneHealth.UNKNOWN
    if in_flight > MAX_OPERATION_CREDITS:
        return BrowserPlaneHealth.DEGRADED
    try:
        from transport_supervisor import recovery_budget_remaining

        if recovery_budget_remaining() <= 0.0:
            return BrowserPlaneHealth.RECOVERING
    except ImportError:
        pass
    return BrowserPlaneHealth.READY


def browser_orchestrator_snapshot() -> BrowserOrchestratorSnapshot:
    mux_available, contexts, wave_leases = _mux_probe()
    in_flight = min(contexts, MAX_OPERATION_CREDITS) if mux_available else 0
    health = _infer_health(
        mux_available=mux_available,
        in_flight=contexts if mux_available else 0,
    )
    return BrowserOrchestratorSnapshot(
        health=health.value,
        operation_credits_max=MAX_OPERATION_CREDITS,
        operation_credits_in_flight=in_flight,
        operation_credits_available=max(0, MAX_OPERATION_CREDITS - in_flight),
        mux_snapshot_available=mux_available,
        mux_contexts=contexts,
        wave_leases=wave_leases,
    )


@contextmanager
def browser_operation_credit_slot(
    *, operation_id: str | None = None
) -> Iterator[str]:
    """P0-B: single entry for mux cold-attach / new_page operation credits."""
    from mux_upstream_admission import upstream_cold_attach_slot

    with upstream_cold_attach_slot(operation_id=operation_id) as op_id:
        yield op_id


def close_exact_targets(
    *,
    target_ids: tuple[str, ...],
    cdp_port: int | None = None,
) -> tuple[int, int]:
    """Close explicit CDP targets through the orchestrator plane (exact-id only)."""
    from infra_browser_registry import close_exact_target, _chrome_port

    port = cdp_port if cdp_port is not None else _chrome_port()
    closed = 0
    failed = 0
    for target_id in target_ids:
        normalized = target_id.strip()
        if not normalized:
            continue
        if close_exact_target(port, normalized):
            closed += 1
        else:
            failed += 1
    return closed, failed


def prune_self_owned_blanks(
    *,
    cdp_port: int | None = None,
    threshold: int = 20,
) -> tuple[int, int, int, int]:
    """Infra dead-owner prune + self-owned blank tabs; orchestrator entry only."""
    import os

    from browser_tab_hygiene import prune_orphan_cdp_pages
    from infra_browser_registry import _chrome_port, prune_infra_registry

    prior = os.environ.get("MYRM_BROWSER_ORCHESTRATOR_PRUNE", "")
    os.environ["MYRM_BROWSER_ORCHESTRATOR_PRUNE"] = "1"
    try:
        port = cdp_port if cdp_port is not None else _chrome_port()
        infra_closed, infra_failed = prune_infra_registry(port)
        orphan_closed, orphan_failed = prune_orphan_cdp_pages(
            cdp_port=port,
            threshold=threshold,
        )
        return infra_closed, infra_failed, orphan_closed, orphan_failed
    finally:
        if prior:
            os.environ["MYRM_BROWSER_ORCHESTRATOR_PRUNE"] = prior
        else:
            os.environ.pop("MYRM_BROWSER_ORCHESTRATOR_PRUNE", None)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Browser Orchestrator CLI (P0-B).")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--prune-self-blanks", action="store_true")
    parser.add_argument("--threshold", type=int, default=20)
    parser.add_argument("--cdp-port", type=int, default=0)
    args = parser.parse_args()
    if args.snapshot:
        import json

        print(json.dumps(browser_orchestrator_snapshot(), sort_keys=True))
        return 0
    if args.prune_self_blanks:
        port = args.cdp_port if args.cdp_port > 0 else None
        infra_closed, infra_failed, orphan_closed, orphan_failed = prune_self_owned_blanks(
            cdp_port=port,
            threshold=args.threshold,
        )
        print(
            "MYRM_BROWSER_ORCHESTRATOR_PRUNE_OK: "
            f"infra_closed={infra_closed} infra_failed={infra_failed} "
            f"orphan_closed={orphan_closed} orphan_failed={orphan_failed}"
        )
        return 0 if infra_failed == 0 and orphan_failed == 0 else 1
    parser.error("--snapshot or --prune-self-blanks is required")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
