"""Coordinator-triggered idle tab hygiene (P0-UX-2 IdleHygieneScheduler).

[INPUT]
- idle_tab_hygiene.idle_prune_self_owned_blanks_if_safe

[OUTPUT]
- run_idle_tab_hygiene_if_safe() → result dict for coordinator reap/finish logs

[POS]
Dev Gate coordinator side-effect only. Never prune during active chrome_e2e BODY.
"""

from __future__ import annotations

import json
from typing import TypedDict


class IdleHygieneSchedulerResult(TypedDict, total=False):
    ok: bool
    skipped: str
    reason: str
    detail: str
    infra_closed: int
    infra_failed: int
    orphan_closed: int
    orphan_failed: int
    active_tests: int
    trigger: str
    orphan_budget: str


def _positive_count(payload: IdleHygieneSchedulerResult, key: str) -> bool:
    value = payload.get(key)
    return isinstance(value, int) and value > 0


def _has_material_hygiene_event(payload: IdleHygieneSchedulerResult) -> bool:
    return any(
        _positive_count(payload, key)
        for key in ("infra_closed", "infra_failed", "orphan_closed", "orphan_failed")
    )


def run_idle_tab_hygiene_if_safe(*, trigger: str) -> IdleHygieneSchedulerResult:
    """Run exact-ownership blank prune when cluster is idle."""
    from idle_tab_hygiene import idle_prune_self_owned_blanks_if_safe  # noqa: PLC0415

    result = idle_prune_self_owned_blanks_if_safe()
    payload: IdleHygieneSchedulerResult = {"trigger": trigger, **result}
    try:
        from chrome_e2e.gates.orphan_budget import evaluate_orphan_budget  # noqa: PLC0415

        budget = evaluate_orphan_budget()
        payload["orphan_budget"] = budget.get("detail", "")
        if not budget.get("ok"):
            print(
                "ORPHAN_BUDGET_WARN: "
                f"{json.dumps(budget, sort_keys=True)}",
                flush=True,
            )
    except ImportError:
        pass
    if result.get("ok") and _has_material_hygiene_event(payload):
        print(
            "IDLE_HYGIENE_SCHEDULER: "
            f"{json.dumps(payload, sort_keys=True)}",
            flush=True,
        )
    elif result.get("skipped") and result.get("skipped") != "active_tests":
        print(
            "IDLE_HYGIENE_SCHEDULER_SKIP: "
            f"{json.dumps(payload, sort_keys=True)}",
            flush=True,
        )
    return payload
