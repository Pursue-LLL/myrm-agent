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
    orphan_closed: int
    trigger: str


def run_idle_tab_hygiene_if_safe(*, trigger: str) -> IdleHygieneSchedulerResult:
    """Run exact-ownership blank prune when cluster is idle."""
    from idle_tab_hygiene import idle_prune_self_owned_blanks_if_safe  # noqa: PLC0415

    result = idle_prune_self_owned_blanks_if_safe()
    payload: IdleHygieneSchedulerResult = {"trigger": trigger, **result}
    if result.get("ok"):
        print(
            "IDLE_HYGIENE_SCHEDULER: "
            f"{json.dumps(payload, sort_keys=True)}",
            flush=True,
        )
    elif result.get("skipped"):
        print(
            "IDLE_HYGIENE_SCHEDULER_SKIP: "
            f"{json.dumps(payload, sort_keys=True)}",
            flush=True,
        )
    return payload
