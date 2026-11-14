"""The shared UI session contract: four-phase UI session isolation, its re-apply after a new chat and the
policy-gated entry point."""

from __future__ import annotations

import asyncio
import sys
import time
import urllib.error
from collections.abc import Awaitable, Callable

from cdp_chat.support import ensure_e2e_search_cleared_in_browser, get_e2e_api_url
from dev_gate.contract import EvaluateIntent

from e2e_core.shared_ui_session.bridge import (
    SharedUiSessionChat,
    _apply_empty_search_block,
    _bridge_probe_ready,
    _ensure_bridge_probe_ready,
    _evaluate_bridge_probe,
    _session_error,
)
from e2e_core.shared_ui_session.caps import (
    _bootstrap_hot_path_fast,
    _bootstrap_hot_path_reused,
    _extend_shared_ui_deadline_if_wall_allows,
    _resolve_bridge_ready_timeout_sec,
)
from e2e_core.shared_ui_session.policy import (
    SearchPolicy,
    _empty_policy_state_key,
    _empty_policy_strong_clear_done,
    _mark_empty_policy_strong_clear_done,
    _normalize_api_url,
    current_search_policy,
)
from e2e_core.shared_ui_session.scripts import HYDRATE_PRIVATE_SEARCH_JS, RESET_GLOBALS_JS, RESET_GLOBALS_KEEP_SEARCH_BLOCK_JS


async def apply_shared_ui_session_contract(
    chat: SharedUiSessionChat,
    *,
    api_url: str | None = None,
    search_policy: SearchPolicy | None = None,
    timeout_sec: float = 90.0,
    deadline: float | None = None,
) -> dict[str, object]:
    """Run RESET_GLOBALS → BIND_API → BRIDGE_READY → SEARCH_POLICY on an owned page."""
    from e2e_session_runtime.lifecycle import assert_phase_budget

    policy = search_policy or current_search_policy()
    if policy is None:
        return {"ok": True, "skipped": True}

    if deadline is not None and time.monotonic() >= deadline:
        deadline = _extend_shared_ui_deadline_if_wall_allows(deadline)
    if deadline is not None and time.monotonic() >= deadline:
        raise _session_error(
            "E2E_SHARED_UI_SESSION", "budget exhausted before RESET_GLOBALS"
        )

    assert_phase_budget("E2E_SHARED_UI_SESSION_RESET")
    try:
        from e2e_session_runtime.lifecycle import touch_wall_progress

        touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_RESET")
    except ImportError:
        pass

    # empty policy two-state contract:
    # 1) first pass per nodeid+api does strong clear;
    # 2) retries use fast-path short-circuit.
    reset_js = (
        RESET_GLOBALS_KEEP_SEARCH_BLOCK_JS if policy == "empty" else RESET_GLOBALS_JS
    )
    print(
        "E2E_SHARED_UI_SESSION_PROGRESS: phase=RESET_GLOBALS",
        file=sys.stderr,
        flush=True,
    )
    reset_raw = await chat.evaluate(
        reset_js,
        intent=EvaluateIntent.BRIDGE_POLL,
    )
    if not isinstance(reset_raw, dict) or reset_raw.get("ok") is not True:
        raise _session_error("E2E_SHARED_UI_SESSION_RESET", reset_raw)

    assert_phase_budget("E2E_SHARED_UI_SESSION_BIND")
    await chat.ensure_e2e_api_base_binding()

    resolved_api = _normalize_api_url(api_url or get_e2e_api_url())

    if policy == "hydrate_private" and _bootstrap_hot_path_fast():
        reused_probe = await _evaluate_bridge_probe(chat)
        if _bridge_probe_ready(reused_probe, policy=policy):
            fast_reason = (
                "reused_warm_shell"
                if _bootstrap_hot_path_reused()
                else "presealed_fast_create"
            )
            print(
                f"E2E_SHARED_UI_SESSION_FASTPATH_HYDRATE: reason={fast_reason}",
                file=sys.stderr,
                flush=True,
            )
            return {
                "ok": True,
                "policy": policy,
                "search": {
                    "ok": True,
                    "phase": "SEARCH_POLICY",
                    "short_circuit": True,
                    "short_circuit_reason": fast_reason,
                },
                "bridge": reused_probe,
            }

    bridge_timeout = _resolve_bridge_ready_timeout_sec(timeout_sec)
    if policy == "hydrate_private" and _bootstrap_hot_path_reused():
        bridge_timeout = max(bridge_timeout, 120.0)
    if deadline is not None:
        # long open_mcp can expire inner bridge_deadline while BODY wall still
        # has budget — mirror rehydrate path extension before fail-fast.
        deadline = _extend_shared_ui_deadline_if_wall_allows(deadline)
        bridge_timeout = min(bridge_timeout, max(0.0, deadline - time.monotonic()))
    if bridge_timeout <= 0:
        raise _session_error(
            "E2E_SHARED_UI_SESSION", "budget exhausted before BRIDGE_READY"
        )

    print(
        "E2E_SHARED_UI_SESSION_PROGRESS: phase=BRIDGE_READY",
        file=sys.stderr,
        flush=True,
    )
    ensure_bridge: Callable[..., Awaitable[None]] | None = getattr(chat, "ensure_react_e2e_bridge", None)
    if callable(ensure_bridge):
        assert_phase_budget("E2E_SHARED_UI_SESSION_BRIDGE")
        try:
            from e2e_session_runtime.lifecycle import touch_wall_progress

            touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_BRIDGE")
        except ImportError:
            pass
        # One bounded reload-recovery extension must reach the inner loop, which then
        # owns the total budget: ensure_react_e2e_bridge() can only extend its own
        # deadline *after* a reload, which work the caller's deadline cannot predict.
        # An outer wait_for pinned to bridge_timeout + 5 would cap the inner loop and
        # re-create the very timeout this extension exists to absorb, so the outer wall
        # grants the same one-time extension.
        bridge_wall = 2 * bridge_timeout + 5.0
        try:
            await asyncio.wait_for(
                ensure_bridge(timeout_sec=bridge_timeout),
                timeout=bridge_wall,
            )
        except TimeoutError as exc:
            raise _session_error(
                "E2E_SHARED_UI_SESSION_BRIDGE",
                {
                    "err": "bridge-ready-timeout",
                    "timeout_sec": bridge_timeout,
                    "wall_sec": bridge_wall,
                    # Distinguish an inner-poll exhaustion (carries the last probe, which
                    # names the missing bridge capability) from the outer wall killing a
                    # hung loop. Without this the two are indistinguishable in logs.
                    "inner": exc.args[0] if exc.args else None,
                },
            ) from exc

    if policy == "empty":
        empty_state_key = _empty_policy_state_key(resolved_api)
        strong_clear_done = _empty_policy_strong_clear_done(empty_state_key)

        # Fast path triggers when either:
        # - block flag survives on the same page; or
        # - strong clear has completed once for this nodeid+api pair.
        search_block_preserved = (
            isinstance(reset_raw, dict)
            and reset_raw.get("searchBlockPreserved") is True
        )
        strong_clear_short_circuit = strong_clear_done and not search_block_preserved

        print(
            f"E2E_SHARED_UI_SESSION_PROGRESS: phase=SEARCH_POLICY empty"
            f"{' (block-preserved)' if search_block_preserved else ''}"
            f"{' (strong-clear-done)' if strong_clear_short_circuit else ''}",
            file=sys.stderr,
            flush=True,
        )

        search_result: dict[str, object] = {
            "ok": True,
            "policy": "empty",
            "phase": "SEARCH_POLICY",
        }

        short_circuit_reason: str | None = None
        if search_block_preserved:
            short_circuit_reason = "block_preserved"
        elif strong_clear_done:
            short_circuit_reason = "strong_clear_done"

        if short_circuit_reason is not None:
            print(
                "E2E_SHARED_UI_SESSION_FASTPATH_EMPTY: "
                f"reason={short_circuit_reason} api={empty_state_key[0]} nodeid={empty_state_key[1]}",
                file=sys.stderr,
                flush=True,
            )
            try:
                from e2e_session_runtime.lifecycle import touch_wall_progress

                touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_FASTPATH_EMPTY")
            except ImportError:
                pass
            search_result["short_circuit"] = True
            search_result["short_circuit_reason"] = short_circuit_reason
        else:
            search_budget = min(45.0, timeout_sec)
            if deadline is not None:
                # extend inner deadline before SEARCH_POLICY (mirror BRIDGE).
                deadline = _extend_shared_ui_deadline_if_wall_allows(deadline)
                search_budget = min(
                    search_budget, max(0.0, deadline - time.monotonic())
                )
            if search_budget <= 0:
                raise _session_error(
                    "E2E_SHARED_UI_SESSION", "budget exhausted before SEARCH_POLICY"
                )
            try:
                await asyncio.wait_for(
                    ensure_e2e_search_cleared_in_browser(
                        chat,
                        api_url=resolved_api,
                        recv_timeout_sec=min(30.0, search_budget),
                        max_attempts=2,
                    ),
                    timeout=search_budget,
                )
                search_result["strong_clear"] = "python_ssot_and_browser_verified"
            except (TimeoutError, RuntimeError, OSError, urllib.error.URLError) as exc:
                print(
                    f"E2E_SHARED_UI_SESSION_WARN: empty search clear fallback block-only err={exc}",
                    file=sys.stderr,
                    flush=True,
                )
                search_result["fallback"] = "block_only"
                search_result["clear_error"] = str(exc)
                search_result["strong_clear"] = "fallback_block_only"

            _mark_empty_policy_strong_clear_done(empty_state_key)

        skip_block: str | None = None
        if short_circuit_reason == "block_preserved":
            skip_block = "block_preserved"
        elif search_result.get("fallback") == "block_only":
            skip_block = "fallback_block_only"
        block_raw = await _apply_empty_search_block(chat, skip_reason=skip_block)
        search_result["block"] = block_raw
    else:
        search_raw = await chat.evaluate(
            HYDRATE_PRIVATE_SEARCH_JS,
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        search_result = (
            search_raw if isinstance(search_raw, dict) else {"value": search_raw}
        )
        if search_result.get("ok") is not True:
            err = str(search_result.get("err") or "")
            if err == "empty-search-configs":
                probe_pre = await _evaluate_bridge_probe(chat)
                if _bridge_probe_ready(probe_pre, policy=policy):
                    print(
                        "E2E_SHARED_UI_SESSION_WARN: hydrate_private search empty — "
                        "bridge ready; continue (chat/workflow legs)",
                        file=sys.stderr,
                        flush=True,
                    )
                    search_result = {
                        "ok": True,
                        "phase": "SEARCH_POLICY",
                        "warn": "empty-search-configs-bridge-ready",
                        "count": 0,
                    }
                    # Probe already verified — skip redundant rehydrate loop (CDP hang under load).
                    return {
                        "ok": True,
                        "policy": policy,
                        "search": search_result,
                        "bridge": probe_pre,
                    }
                else:
                    raise _session_error("E2E_SHARED_UI_SESSION_SEARCH", search_result)
            else:
                raise _session_error("E2E_SHARED_UI_SESSION_SEARCH", search_result)

    probe = await _ensure_bridge_probe_ready(
        chat,
        policy=policy,
        timeout_sec=timeout_sec,
        deadline=deadline,
    )

    return {
        "ok": True,
        "policy": policy,
        "search": search_result,
        "bridge": probe,
    }


async def reapply_shared_ui_session_after_new_chat(
    chat: SharedUiSessionChat,
    *,
    deadline: float | None = None,
) -> dict[str, object] | None:
    """After resetChat when bootstrap already ran full contract — avoid Page.reload.

    Re-bind empty search block and probe bridge; fall back to full contract only if probe fails.
    """
    policy = current_search_policy()
    if policy is None:
        return None
    if not isinstance(chat, SharedUiSessionChat):
        raise TypeError("E2E_SHARED_UI_SESSION: chat session missing evaluate hooks")

    print(
        "E2E_SHARED_UI_SESSION_REAPPLY: phase=after_new_chat lightweight",
        file=sys.stderr,
        flush=True,
    )
    try:
        from e2e_session_runtime.lifecycle import touch_wall_progress

        touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_REAPPLY")
    except ImportError:
        pass

    search_result: dict[str, object] | None = None
    if policy == "empty":
        search_result = await _apply_empty_search_block(
            chat,
            skip_reason="block_preserved",
        )

    probe = await _evaluate_bridge_probe(chat)
    if _bridge_probe_ready(probe, policy=policy):
        return {
            "ok": True,
            "policy": policy,
            "reapply": "lightweight",
            "search": search_result,
            "bridge": probe,
        }

    print(
        "E2E_SHARED_UI_SESSION_REAPPLY: bridge probe stale — full contract fallback "
        f"probe={probe}",
        file=sys.stderr,
        flush=True,
    )
    return await apply_shared_ui_session_contract(
        chat,
        search_policy=policy,
        deadline=deadline,
    )


async def maybe_apply_shared_ui_session_contract(
    chat: object,
    *,
    api_url: str | None = None,
    timeout_sec: float = 90.0,
    deadline: float | None = None,
) -> dict[str, object] | None:
    """No-op unless MYRM_E2E_SEARCH_POLICY is set by chrome_e2e conftest."""
    if current_search_policy() is None:
        return None
    if not isinstance(chat, SharedUiSessionChat):
        raise TypeError("E2E_SHARED_UI_SESSION: chat session missing evaluate hooks")
    return await apply_shared_ui_session_contract(
        chat,
        api_url=api_url,
        timeout_sec=timeout_sec,
        deadline=deadline,
    )
