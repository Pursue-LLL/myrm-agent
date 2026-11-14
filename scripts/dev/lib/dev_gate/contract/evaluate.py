"""Budgets of CDP evaluate calls, keyed by what the call is for."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from dev_gate.contract.attach import E2E_ATTACH_CDP_GRACE_SEC, E2E_ATTACH_FRONTEND_MS, _sync_probe_cdp_timeout_sec

# --- EvaluateIntent SSOT (§24 W3) ---


class EvaluateIntent(StrEnum):
    """CDP evaluate semantic intent — drives awaitPromise, timeout, MUX retry."""

    SYNC_PROBE = "sync_probe"
    BRIDGE_POLL = "bridge_poll"
    ROUTE_ATTACH = "route_attach"
    AGENT_SUBMIT = "agent_submit"
    NAV_HEAVY = "nav_heavy"


@dataclass(frozen=True)
class EvaluateBudget:
    await_promise: bool
    cdp_timeout_sec: float
    mux_max_attempts: int
    mux_recv_grace_sec: float


def resolve_evaluate_budget(
    intent: EvaluateIntent,
    *,
    live: bool = True,
) -> EvaluateBudget:
    """Single SSOT for evaluate budgets — no scattered magic timeouts."""
    if intent is EvaluateIntent.SYNC_PROBE:
        return EvaluateBudget(
            await_promise=False,
            cdp_timeout_sec=_sync_probe_cdp_timeout_sec(live=live),
            mux_max_attempts=0,
            mux_recv_grace_sec=5.0,
        )
    if intent is EvaluateIntent.BRIDGE_POLL:
        return EvaluateBudget(
            await_promise=False,
            cdp_timeout_sec=45.0 if live else 15.0,
            mux_max_attempts=1,
            mux_recv_grace_sec=10.0,
        )
    if intent is EvaluateIntent.ROUTE_ATTACH:
        attach_sec = E2E_ATTACH_FRONTEND_MS / 1000.0 + E2E_ATTACH_CDP_GRACE_SEC
        return EvaluateBudget(
            await_promise=True,
            cdp_timeout_sec=attach_sec,
            mux_max_attempts=2,
            mux_recv_grace_sec=15.0,
        )
    if intent is EvaluateIntent.AGENT_SUBMIT:
        return EvaluateBudget(
            await_promise=True,
            cdp_timeout_sec=180.0,
            mux_max_attempts=2,
            mux_recv_grace_sec=15.0,
        )
    # NAV_HEAVY — aligned with W4 silk path operation budgets
    return EvaluateBudget(
        await_promise=False,
        cdp_timeout_sec=120.0,
        mux_max_attempts=1,
        mux_recv_grace_sec=20.0,
    )
