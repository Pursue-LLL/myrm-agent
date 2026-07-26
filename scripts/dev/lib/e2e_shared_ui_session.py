"""Shared :3000 UI session contract for parallel chrome_e2e (Dev Gate SSOT).

[INPUT]
cdp_chat_support::ensure_e2e_search_cleared_in_browser (POS: E2E API/chat 消息 SSOT)
cdp_chat_support::get_e2e_api_url (POS: E2E API/chat 消息 SSOT)

[OUTPUT]
apply_shared_ui_session_contract: 四阶段 UI 会话隔离（RESET → BIND → BRIDGE → SEARCH）
prime_search_policy_env / resolve_search_policy_from_item: pytest marker → env SSOT

[POS]
Dev Gate 层共享 UI 污染隔离。每 chrome_e2e item 在 bootstrap / new-chat 后重置 window 全局状态。
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import urllib.error
from typing import Literal, Protocol, runtime_checkable

from cdp_chat_support import ensure_e2e_search_cleared_in_browser, get_e2e_api_url

E2E_SEARCH_POLICY_ENV = "MYRM_E2E_SEARCH_POLICY"
SearchPolicy = Literal["empty", "hydrate_private"]
DEFAULT_SEARCH_POLICY: SearchPolicy = "hydrate_private"

RESET_GLOBALS_JS = """(() => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  window.__MYRM_E2E_DIRECT_SSE__ = false;
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.abortActiveStream?.();
  bridge?.releaseActiveStreamForApiResume?.();
  bridge?.clearSseSnapshot?.();
  return { ok: true, phase: 'RESET_GLOBALS' };
})()"""

HYDRATE_PRIVATE_SEARCH_JS = """(async () => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.syncSearchServicesFromE2eApi) {
    return { ok: false, err: 'no-bridge', phase: 'SEARCH_POLICY' };
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const sync = await bridge.syncSearchServicesFromE2eApi();
    if (sync?.ok && (sync.count ?? 0) > 0) {
      return { ok: true, count: sync.count, phase: 'SEARCH_POLICY' };
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
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
  hasProgressSnap:
    typeof window.__MYRM_E2E_CHAT__?.getFastSearchProgressSnapshot === 'function',
  blockSearchSync: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__),
  phase: 'BRIDGE_READY',
}))()"""


@runtime_checkable
class SharedUiSessionChat(Protocol):
    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        recv_timeout: float = 30.0,
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


def _session_error(token: str, detail: object) -> RuntimeError:
    return RuntimeError(f"{token}: {detail}")


async def apply_shared_ui_session_contract(
    chat: SharedUiSessionChat,
    *,
    api_url: str | None = None,
    search_policy: SearchPolicy | None = None,
    timeout_sec: float = 90.0,
    deadline: float | None = None,
) -> dict[str, object]:
    """Run RESET_GLOBALS → BIND_API → BRIDGE_READY → SEARCH_POLICY on an owned page."""
    policy = search_policy or current_search_policy()
    if policy is None:
        return {"ok": True, "skipped": True}

    if deadline is not None and time.monotonic() >= deadline:
        raise _session_error("E2E_SHARED_UI_SESSION", "budget exhausted before RESET_GLOBALS")

    print(
        "E2E_SHARED_UI_SESSION_PROGRESS: phase=RESET_GLOBALS",
        file=sys.stderr,
        flush=True,
    )
    reset_raw = await chat.evaluate(
        RESET_GLOBALS_JS,
        await_promise=False,
        recv_timeout=15.0,
    )
    if not isinstance(reset_raw, dict) or reset_raw.get("ok") is not True:
        raise _session_error("E2E_SHARED_UI_SESSION_RESET", reset_raw)

    await chat.ensure_e2e_api_base_binding()

    resolved_api = (api_url or get_e2e_api_url()).rstrip("/")

    bridge_timeout = min(60.0, timeout_sec)
    if deadline is not None:
        bridge_timeout = min(bridge_timeout, max(0.0, deadline - time.monotonic()))
    if bridge_timeout <= 0:
        raise _session_error("E2E_SHARED_UI_SESSION", "budget exhausted before BRIDGE_READY")

    print(
        "E2E_SHARED_UI_SESSION_PROGRESS: phase=BRIDGE_READY",
        file=sys.stderr,
        flush=True,
    )
    ensure_bridge = getattr(chat, "ensure_react_e2e_bridge", None)
    if callable(ensure_bridge):
        await ensure_bridge(timeout_sec=bridge_timeout)

    if policy == "empty":
        print(
            "E2E_SHARED_UI_SESSION_PROGRESS: phase=SEARCH_POLICY empty",
            file=sys.stderr,
            flush=True,
        )
        search_budget = min(45.0, timeout_sec)
        if deadline is not None:
            search_budget = min(search_budget, max(0.0, deadline - time.monotonic()))
        if search_budget <= 0:
            raise _session_error("E2E_SHARED_UI_SESSION", "budget exhausted before SEARCH_POLICY")
        search_result: dict[str, object] = {
            "ok": True,
            "policy": "empty",
            "phase": "SEARCH_POLICY",
        }
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
        except (TimeoutError, RuntimeError, OSError, urllib.error.URLError) as exc:
            # Empty-policy fallback: always block browser-side sync even if API clear timed out.
            print(
                f"E2E_SHARED_UI_SESSION_WARN: empty search clear fallback block-only err={exc}",
                file=sys.stderr,
                flush=True,
            )
            search_result["fallback"] = "block_only"
            search_result["clear_error"] = str(exc)
        block_raw = await chat.evaluate(
            SET_EMPTY_SEARCH_BLOCK_JS,
            await_promise=False,
            recv_timeout=15.0,
        )
        if not isinstance(block_raw, dict) or block_raw.get("ok") is not True:
            raise _session_error("E2E_SHARED_UI_SESSION_SEARCH", block_raw)
    else:
        search_raw = await chat.evaluate(
            HYDRATE_PRIVATE_SEARCH_JS,
            await_promise=True,
            recv_timeout=45.0,
        )
        search_result = search_raw if isinstance(search_raw, dict) else {"value": search_raw}
        if search_result.get("ok") is not True:
            raise _session_error("E2E_SHARED_UI_SESSION_SEARCH", search_result)

    probe_raw = await chat.evaluate(
        BRIDGE_READY_PROBE_JS,
        await_promise=False,
        recv_timeout=15.0,
    )
    probe = probe_raw if isinstance(probe_raw, dict) else {"value": probe_raw}
    if probe.get("hasSendChatMessage") is not True:
        raise _session_error("E2E_SHARED_UI_SESSION_BRIDGE", probe)

    if policy == "empty" and probe.get("blockSearchSync") is not True:
        raise _session_error(
            "E2E_SHARED_UI_SESSION_BRIDGE",
            {"err": "empty-policy-requires-block-flag", "probe": probe},
        )

    return {
        "ok": True,
        "policy": policy,
        "search": search_result,
        "bridge": probe,
    }


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
