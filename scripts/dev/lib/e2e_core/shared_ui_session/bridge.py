"""Bridge-ready probe with its CDP re-hydrate loop and the empty search block write, plus the chat protocol
they run against."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Protocol, runtime_checkable

from dev_gate.contract import EvaluateIntent

from e2e_core.shared_ui_session.caps import _extend_shared_ui_deadline_if_wall_allows
from e2e_core.shared_ui_session.policy import SearchPolicy
from e2e_core.shared_ui_session.scripts import BRIDGE_READY_PROBE_JS, SET_EMPTY_SEARCH_BLOCK_JS

BRIDGE_PROBE_MAX_REHYDRATE = 3


@runtime_checkable
class SharedUiSessionChat(Protocol):
    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        recv_timeout: float = 30.0,
        intent: EvaluateIntent | None = None,
    ) -> object: ...

    async def ensure_e2e_api_base_binding(self) -> None: ...

    async def ensure_react_e2e_bridge(self, *, timeout_sec: float = 90.0) -> None: ...


def _session_error(token: str, detail: object) -> RuntimeError:
    return RuntimeError(f"{token}: {detail}")


async def _evaluate_bridge_probe(chat: SharedUiSessionChat) -> dict[str, object]:
    probe_raw = await chat.evaluate(
        BRIDGE_READY_PROBE_JS,
        intent=EvaluateIntent.BRIDGE_POLL,
    )
    return probe_raw if isinstance(probe_raw, dict) else {"value": probe_raw}


def _bridge_probe_ready(probe: dict[str, object], *, policy: SearchPolicy) -> bool:
    if probe.get("hasSendChatMessage") is not True:
        return False
    if probe.get("hasSubmitAndObserveTurn") is not True:
        return False
    return not (policy == "empty" and probe.get("blockSearchSync") is not True)


async def _apply_empty_search_block(
    chat: SharedUiSessionChat,
    *,
    skip_reason: str | None = None,
) -> dict[str, object]:
    """Set empty-search block flag; skip redundant mux evaluate on fast paths."""
    if skip_reason in ("block_preserved", "fallback_block_only"):
        return {"ok": True, "phase": "SEARCH_POLICY", "skipped": skip_reason}
    if skip_reason != "force":
        try:
            probe = await chat.evaluate(
                "(() => ({ ok: true, blocked: !!window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ }))()",
                intent=EvaluateIntent.SYNC_PROBE,
            )
        except (RuntimeError, TimeoutError):
            probe = None
        if isinstance(probe, dict) and probe.get("blocked") is True:
            return {"ok": True, "phase": "SEARCH_POLICY", "skipped": "already_blocked"}
    try:
        from e2e_session_runtime.lifecycle import touch_wall_progress

        touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_SEARCH_BLOCK")
    except ImportError:
        pass
    block_raw = await chat.evaluate(
        SET_EMPTY_SEARCH_BLOCK_JS,
        intent=EvaluateIntent.BRIDGE_POLL,
    )
    if not isinstance(block_raw, dict) or block_raw.get("ok") is not True:
        raise _session_error("E2E_SHARED_UI_SESSION_SEARCH", block_raw)
    return block_raw


async def _ensure_bridge_probe_ready(
    chat: SharedUiSessionChat,
    *,
    policy: SearchPolicy,
    timeout_sec: float,
    deadline: float | None,
) -> dict[str, object]:
    """Final bridge probe with CDP re-hydrate retries after SEARCH_POLICY side effects."""
    from e2e_session_runtime.lifecycle import assert_phase_budget

    ensure_bridge = getattr(chat, "ensure_react_e2e_bridge", None)
    last_probe: dict[str, object] = {}

    for rehydrate_pass in range(BRIDGE_PROBE_MAX_REHYDRATE + 1):
        last_probe = await _evaluate_bridge_probe(chat)
        if _bridge_probe_ready(last_probe, policy=policy):
            return last_probe

        if not callable(ensure_bridge) or rehydrate_pass >= BRIDGE_PROBE_MAX_REHYDRATE:
            break

        attempt = rehydrate_pass + 1
        print(
            "E2E_SHARED_UI_SESSION_BRIDGE_REHYDRATE: "
            f"attempt={attempt}/{BRIDGE_PROBE_MAX_REHYDRATE} probe={last_probe}",
            file=sys.stderr,
            flush=True,
        )

        rehydrate_base = 45.0
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
            try:
                from dev_gate.contract.parallel_pressure import parallel_signoff_pressure_peers

                peers = parallel_signoff_pressure_peers()
                if peers >= 2:
                    rehydrate_base = min(120.0, 45.0 + peers * 8.0)
            except ImportError:
                pass
        rehydrate_timeout = min(rehydrate_base, timeout_sec)
        if deadline is not None:
            deadline = _extend_shared_ui_deadline_if_wall_allows(deadline)
            rehydrate_timeout = min(
                rehydrate_timeout, max(0.0, deadline - time.monotonic())
            )
        if rehydrate_timeout <= 0:
            raise _session_error(
                "E2E_SHARED_UI_SESSION",
                "budget exhausted before BRIDGE rehydrate",
            )

        assert_phase_budget("E2E_SHARED_UI_SESSION_BRIDGE")
        try:
            from e2e_session_runtime.lifecycle import touch_wall_progress

            touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_BRIDGE_REHYDRATE")
        except ImportError:
            pass

        await chat.ensure_e2e_api_base_binding()
        try:
            await asyncio.wait_for(
                ensure_bridge(timeout_sec=rehydrate_timeout),
                timeout=rehydrate_timeout + 5.0,
            )
        except TimeoutError as exc:
            if rehydrate_pass >= BRIDGE_PROBE_MAX_REHYDRATE - 1:
                raise _session_error(
                    "E2E_SHARED_UI_SESSION_BRIDGE",
                    {
                        "err": "bridge-rehydrate-timeout",
                        "probe": last_probe,
                        "attempt": attempt,
                    },
                ) from exc
            await asyncio.sleep(min(2.0 * attempt, 6.0))
            continue

        if policy == "empty":
            await _apply_empty_search_block(chat, skip_reason="force")

        await asyncio.sleep(0.5)

    if (
        policy == "empty"
        and last_probe.get("hasSendChatMessage") is True
        and last_probe.get("blockSearchSync") is not True
    ):
        await _apply_empty_search_block(chat, skip_reason="force")
        last_probe = await _evaluate_bridge_probe(chat)
        if _bridge_probe_ready(last_probe, policy=policy):
            return last_probe

    raise _session_error("E2E_SHARED_UI_SESSION_BRIDGE", last_probe)
