"""Shared :3000 UI session contract for parallel chrome_e2e (Dev Gate SSOT).

[INPUT]
cdp_chat_support::ensure_e2e_search_cleared_in_browser (POS: E2E API/chat 消息 SSOT)
cdp_chat_support::get_e2e_api_url (POS: E2E API/chat 消息 SSOT)

[OUTPUT]
apply_shared_ui_session_contract: 四阶段 UI 会话隔离（RESET → BIND → BRIDGE → SEARCH）+ 最终 probe 失败时 CDP re-hydrate（最多 3 次）
prime_search_policy_env / resolve_search_policy_from_item: pytest marker → env SSOT
RESET_GLOBALS_KEEP_SEARCH_BLOCK_JS: empty 策略专用 RESET 变体（保留 __MYRM_E2E_BLOCK_SEARCH_SYNC__）

[POS]
Dev Gate 层共享 UI 污染隔离。每 chrome_e2e item 在 bootstrap / new-chat 后重置 window 全局状态。
empty 策略使用两态契约：同 nodeid+api 首轮强一致清理；后续重试快路径 short-circuit。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import urllib.error
from typing import Literal, Protocol, runtime_checkable

from cdp_chat_support import ensure_e2e_search_cleared_in_browser, get_e2e_api_url
from dev_gate_contract import EvaluateIntent

E2E_SEARCH_POLICY_ENV = "MYRM_E2E_SEARCH_POLICY"
SearchPolicy = Literal["empty", "hydrate_private"]
DEFAULT_SEARCH_POLICY: SearchPolicy = "hydrate_private"
_EMPTY_POLICY_STRONG_CLEAR_DONE: set[tuple[str, str]] = set()
_PARALLEL_BRIDGE_READY_CAP_SEC = 180.0
_SIGNOFF_PARALLEL_BRIDGE_READY_CAP_SEC = 240.0
_SERIAL_BRIDGE_READY_CAP_SEC = 60.0


def _parallel_bridge_ready_cap_sec() -> float:
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return _SIGNOFF_PARALLEL_BRIDGE_READY_CAP_SEC
    return _PARALLEL_BRIDGE_READY_CAP_SEC


def _resolve_bridge_ready_timeout_sec(timeout_sec: float) -> float:
    """Parallel SHPOIB hydrate queue can defer React mount beyond 60s."""
    from dev_gate_contract import shared_ui_hydrate_wait_sec
    from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

    if parallel_shared_ui_hydrate_queue_enabled():
        parallel_cap = min(
            _parallel_bridge_ready_cap_sec(), float(shared_ui_hydrate_wait_sec())
        )
        return min(parallel_cap, timeout_sec)
    return min(_SERIAL_BRIDGE_READY_CAP_SEC, timeout_sec)


RESET_GLOBALS_JS = """(() => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  window.__MYRM_E2E_DIRECT_SSE__ = false;
  window.__MYRM_E2E_SEND_GENERATION__ = (window.__MYRM_E2E_SEND_GENERATION__ ?? 0) + 1;
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.abortActiveStream?.();
  bridge?.releaseActiveStreamForApiResume?.();
  bridge?.clearSseSnapshot?.();
  return { ok: true, phase: 'RESET_GLOBALS' };
})()"""

RESET_GLOBALS_KEEP_SEARCH_BLOCK_JS = """(() => {
  window.__MYRM_E2E_DIRECT_SSE__ = false;
  window.__MYRM_E2E_SEND_GENERATION__ = (window.__MYRM_E2E_SEND_GENERATION__ ?? 0) + 1;
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.abortActiveStream?.();
  bridge?.releaseActiveStreamForApiResume?.();
  bridge?.clearSseSnapshot?.();
  return { ok: true, phase: 'RESET_GLOBALS', searchBlockPreserved: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__) };
})()"""

HYDRATE_PRIVATE_SEARCH_JS = """(async () => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  // BRIDGE_READY may pass, then a parallel warm-shell reclaim / navigate can
  // reload the page and momentarily drop __MYRM_E2E_CHAT__ before React remounts
  // the bridge. Fail-fast on a transient no-bridge strands the SEARCH_POLICY
  // contract; instead poll for the bridge inside the deadline like BRIDGE_READY.
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const liveBridge = window.__MYRM_E2E_CHAT__;
    if (liveBridge?.syncSearchServicesFromE2eApi) {
      const sync = await liveBridge.syncSearchServicesFromE2eApi();
      if (sync?.ok) {
        return { ok: true, count: sync.count, phase: 'SEARCH_POLICY' };
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  const finalBridge = window.__MYRM_E2E_CHAT__;
  if (!finalBridge?.syncSearchServicesFromE2eApi) {
    return { ok: false, err: 'no-bridge', phase: 'SEARCH_POLICY' };
  }
  return { ok: false, err: 'empty-search-configs', phase: 'SEARCH_POLICY' };
})()"""

SET_EMPTY_SEARCH_BLOCK_JS = """(() => {
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  return { ok: true, phase: 'SEARCH_POLICY' };
})()"""

BRIDGE_READY_PROBE_JS = """(() => ({
  hasBridge: Boolean(window.__MYRM_E2E_CHAT__),
  hasSendChatMessage: typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function',
  hasAttach: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
  hasProgressSnap:
    typeof window.__MYRM_E2E_CHAT__?.getFastSearchProgressSnapshot === 'function',
  blockSearchSync: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__),
  phase: 'BRIDGE_READY',
}))()"""

BRIDGE_PROBE_MAX_REHYDRATE = 3


def _normalize_api_url(api_url: str) -> str:
    return api_url.rstrip("/")


def _current_pytest_node_id() -> str:
    raw = os.environ.get("PYTEST_CURRENT_TEST", "").strip()
    if not raw:
        return "global"
    node_id = raw.partition(" (")[0].strip()
    return node_id or "global"


def _empty_policy_state_key(api_url: str) -> tuple[str, str]:
    return (_normalize_api_url(api_url), _current_pytest_node_id())


def _empty_policy_strong_clear_done(key: tuple[str, str]) -> bool:
    return key in _EMPTY_POLICY_STRONG_CLEAR_DONE


def _mark_empty_policy_strong_clear_done(key: tuple[str, str]) -> None:
    _EMPTY_POLICY_STRONG_CLEAR_DONE.add(key)


def _reset_empty_policy_runtime_state_for_tests() -> None:
    _EMPTY_POLICY_STRONG_CLEAR_DONE.clear()


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


def resolve_search_policy_from_item(item: object) -> SearchPolicy:
    """Map pytest markers to shared UI search policy (default hydrate_private)."""
    get_marker = getattr(item, "get_closest_marker", None)
    if not callable(get_marker):
        return DEFAULT_SEARCH_POLICY

    policy_marker = get_marker("e2e_search_policy")
    if policy_marker is not None:
        raw = (
            policy_marker.args[0]
            if policy_marker.args
            else policy_marker.kwargs.get("policy")
        )
        policy = str(raw or "").strip()
        if policy in ("empty", "hydrate_private"):
            return policy  # type: ignore[return-value]
        raise ValueError(
            f"Invalid e2e_search_policy marker value {raw!r}; "
            "expected 'empty' or 'hydrate_private'"
        )

    if get_marker("requires_empty_search_services") is not None:
        return "empty"

    return DEFAULT_SEARCH_POLICY


def prime_search_policy_env(item: object) -> SearchPolicy:
    """Persist resolved policy for bootstrap hooks (conftest autouse)."""
    policy = resolve_search_policy_from_item(item)
    os.environ[E2E_SEARCH_POLICY_ENV] = policy
    print(
        f"E2E_SHARED_UI_SESSION_POLICY: policy={policy}",
        file=sys.stderr,
        flush=True,
    )
    return policy


def current_search_policy() -> SearchPolicy | None:
    raw = os.environ.get(E2E_SEARCH_POLICY_ENV, "").strip()
    if raw in ("empty", "hydrate_private"):
        return raw  # type: ignore[return-value]
    return None


def _bootstrap_hot_path_reused() -> bool:
    return os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "reused"


def _bootstrap_hot_path_fast() -> bool:
    if _bootstrap_hot_path_reused():
        return True
    return (
        os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1"
        and os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "fast_create"
    )


def _session_error(token: str, detail: object) -> RuntimeError:
    return RuntimeError(f"{token}: {detail}")


def _shared_ui_deadline_extend_cap_sec() -> float:
    """Scale shared UI contract extension under parallel mux pressure (v2.2)."""
    base = 90.0
    try:
        from dev_gate_contract import _parallel_chrome_e2e_pressure

        peers = _parallel_chrome_e2e_pressure()
        if peers >= 2:
            return min(180.0, base + peers * 15.0)
    except ImportError:
        pass
    return base


def _extend_shared_ui_deadline_if_wall_allows(
    deadline: float | None,
) -> float | None:
    """Extend an expired inner deadline when outer bootstrap/body wall still has budget."""
    if deadline is None or time.monotonic() < deadline:
        return deadline
    from e2e_session_runtime.lifecycle import current_phase, remaining_wall_sec

    remaining = remaining_wall_sec()
    extend_floor = 20.0 if os.environ.get("E2E_SIGNOFF", "").strip() == "1" else 45.0
    phase = current_phase()
    if phase not in {"bootstrap", "body"} or remaining <= extend_floor:
        return deadline
    extend_cap = _shared_ui_deadline_extend_cap_sec()
    return time.monotonic() + min(extend_cap, remaining - 10.0)


async def _evaluate_bridge_probe(chat: SharedUiSessionChat) -> dict[str, object]:
    probe_raw = await chat.evaluate(
        BRIDGE_READY_PROBE_JS,
        intent=EvaluateIntent.BRIDGE_POLL,
    )
    return probe_raw if isinstance(probe_raw, dict) else {"value": probe_raw}


def _bridge_probe_ready(probe: dict[str, object], *, policy: SearchPolicy) -> bool:
    if probe.get("hasSendChatMessage") is not True:
        return False
    if policy == "empty" and probe.get("blockSearchSync") is not True:
        return False
    return True


async def _apply_empty_search_block(
    chat: SharedUiSessionChat,
    *,
    skip_reason: str | None = None,
) -> dict[str, object]:
    """Set empty-search block flag; skip redundant mux evaluate on fast paths (R229)."""
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
                from dev_gate_contract import _parallel_signoff_pressure_peers

                peers = _parallel_signoff_pressure_peers()
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

    # R56: empty policy two-state contract:
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
        # R269: long open_mcp can expire inner bridge_deadline while BODY wall still
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
    ensure_bridge = getattr(chat, "ensure_react_e2e_bridge", None)
    if callable(ensure_bridge):
        assert_phase_budget("E2E_SHARED_UI_SESSION_BRIDGE")
        try:
            from e2e_session_runtime.lifecycle import touch_wall_progress

            touch_wall_progress(current_node="E2E_SHARED_UI_SESSION_BRIDGE")
        except ImportError:
            pass
        bridge_wall = bridge_timeout + 5.0
        try:
            await asyncio.wait_for(
                ensure_bridge(timeout_sec=bridge_timeout),
                timeout=bridge_wall,
            )
        except TimeoutError as exc:
            raise _session_error(
                "E2E_SHARED_UI_SESSION_BRIDGE",
                {"err": "bridge-ready-timeout", "timeout_sec": bridge_timeout},
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
                # R272: extend inner deadline before SEARCH_POLICY (mirror R269 BRIDGE).
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
    """After resetChat when bootstrap already ran full contract — avoid Page.reload (R124).

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
