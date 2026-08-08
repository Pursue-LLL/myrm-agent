"""Chrome READ E2E: Memory lifecycle timeline + extract retry on real Web Chat."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (
    _coerce_evaluate_result,
    _require_e2e_cdp_ready,
    _restore_e2e_window_via_cdp,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_MAX_ATTEMPTS = 2
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Runtime.evaluate",
    "Browser Orchestrator",
    "CDP request timeout",
    "Page.navigate",
    "Chrome MCP",
    "connection reset",
    "wait_for_state",
    "Browser state did not become ready",
    "attachToChat",
    "no-bridge",
    "Page shell did not hydrate",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
    "recover_mux",
    "chrome-error",
    "warm_ui_route",
    "Connection refused",
    "E2E_ORCHESTRATOR_LEASE_DENIED",
    "ORCHESTRATOR_LEASE_DENIED",
    "wave is not open",
    "PARENT_LEASE_NOT_ACTIVE",
    "E2E_LEASE_INVALID",
    "LEASE_NOT_ACTIVE",
    "MUX_ATTACH_RESTART_BLOCKED_PARALLEL",
    "timed out",
    "QueuePool limit",
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _attach_eval_timeout_sec() -> float:
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 150.0
    except ImportError:
        pass
    return 120.0


def _attach_memory_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const hasAssistant = msgs.some((m) => m?.role === 'assistant');
  return {{
    ok:
      snap.chatId === {chat_id_json}
      && hasAssistant
      && Boolean(store?.isMessagesLoaded)
      && !Boolean(store?.notFound)
      && !Boolean(store?.loadError),
    snap,
    msgCount: msgs.length,
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
    loadError: Boolean(store?.loadError),
    notFound: Boolean(store?.notFound),
  }};
}})()"""


def _await_attach_memory_chat(
    client: object,
    page: object,
    chat_id: str,
    *,
    timeout_sec: float = 120.0,
    ui_url: str | None = None,
) -> dict[str, object]:
    home_url = f"{get_e2e_ui_url().rstrip('/')}/"
    chat_url = f"{get_e2e_ui_url().rstrip('/')}/{chat_id}"
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        remaining = max(5.0, deadline - time.monotonic())
        try:
            raw = client.evaluate(  # type: ignore[attr-defined]
                page,
                _attach_memory_chat_probe(chat_id),
                timeout_sec=min(75.0, _attach_eval_timeout_sec(), remaining),
            )
        except RuntimeError as exc:
            if "CDP request timeout" not in str(exc) and "Runtime.evaluate" not in str(
                exc
            ):
                raise
            last = {"err": str(exc)}
            time.sleep(2.0)
            continue
        if isinstance(raw, dict) and raw.get("ok") is True:
            return raw
        if isinstance(raw, dict) and raw.get("err") == "no-bridge":
            client.navigate(page, home_url)  # type: ignore[attr-defined]
            time.sleep(1.5)
            if ui_url:
                _ensure_react_bridge_on_home(client, page, ui_url=ui_url)
            else:
                wait_for_react_e2e_bridge(  # type: ignore[arg-type]
                    client,  # type: ignore[arg-type]
                    page,  # type: ignore[arg-type]
                    timeout_sec=min(90.0, remaining),
                    page_url=home_url,
                )
            client.navigate(page, chat_url)  # type: ignore[attr-defined]
            time.sleep(1.5)
            dismiss_blocking_modals(client, page, recover_url=chat_url)  # type: ignore[arg-type]
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
        last = raw if isinstance(raw, dict) else {"value": raw}
        time.sleep(2.0)
    raise AssertionError(f"attachToChat did not hydrate memory lifecycle chat: {last}")


def _ensure_react_bridge_on_home(
    client: object,
    page: object,
    *,
    ui_url: str,
) -> dict[str, object]:
    home_url = f"{ui_url.rstrip('/')}/"
    dismiss_blocking_modals(client, page, recover_url=home_url)  # type: ignore[arg-type]
    client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
    bridge_ready = wait_for_react_e2e_bridge(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        timeout_sec=_bridge_ready_timeout_sec(),
        page_url=home_url,
    )
    assert bridge_ready.get("ready") is True, json.dumps(
        bridge_ready, ensure_ascii=False
    )
    return bridge_ready


_CHAT_HYDRATED_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const hasAssistant = msgs.some((m) => m?.role === 'assistant');
  return {
    ready: Boolean(store?.isMessagesLoaded && !store?.loading && hasAssistant),
    msgCount: msgs.length,
    loading: Boolean(store?.loading),
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
  };
})()"""

_CHAT_UI_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const hasStore =
    Boolean(store?.isMessagesLoaded)
    && (store?.messages?.length ?? 0) >= 2
    && store.messages.some((m) => m?.role === 'assistant');
  const assistant = document.querySelector('[data-test-id="assistant-message"]');
  // textContent (not innerText): innerText is '' while the window is offscreen-hidden.
  const text = document.body?.textContent || '';
  const hasNoted = /Noted|remember your food|cilantro/i.test(text);
  const msgDomCount = document.querySelectorAll('[data-message-id]').length;
  const path = window.location.pathname.replace(/^\\//, '');
  // Window policy is OFFSCREEN-NORMAL (never minimized). If a window ever goes
  // hidden again, Chrome pauses rAF and React stops rendering — the UI stays on
  // its SSR skeleton while the store is already hydrated. Force ready=false and
  // surface __windowHidden so wait_for_state restores the window instead of
  // silently failing on a frozen skeleton.
  const visibility = document.visibilityState;
  const windowHidden = visibility === 'hidden';
  return {
    ready:
      !windowHidden && hasStore && Boolean(assistant) && hasNoted && msgDomCount >= 2,
    __windowHidden: windowHidden,
    hasStore,
    hasAssistant: Boolean(assistant),
    hasNoted,
    msgDomCount,
    bodyLen: text.length,
    snippet: text.slice(0, 400),
    path,
    storeChatId: store?.chatId ?? null,
    notFound: Boolean(store?.notFound),
    loadError: Boolean(store?.loadError),
    hasMessageListSkeleton: Boolean(
      document.querySelector('[data-testid="message-list-skeleton"]'),
    ),
    hasChatRouteLoading: Boolean(
      document.querySelector('[data-testid="chat-route-loading"]'),
    ),
    readyState: document.readyState,
    title: document.title || '',
  };
})()"""

_ROUTE_SEGMENT_CLEARED_JS = """(() => ({
  ready: !document.querySelector('[data-testid="chat-route-loading"]'),
  hasChatRouteLoading: Boolean(
    document.querySelector('[data-testid="chat-route-loading"]'),
  ),
}))()"""


def _probe_chat_ui_state(
    client: object,
    page: object,
    *,
    timeout_sec: float = 30.0,
) -> dict[str, object]:
    """Poll chat UI readiness without raising — enables skeleton reload recovery."""
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {"ready": False}
    while time.monotonic() < deadline:
        try:
            raw = client.evaluate(  # type: ignore[attr-defined]
                page,
                _CHAT_UI_READY_JS,
                timeout_sec=min(15.0, max(5.0, deadline - time.monotonic())),
            )
            last = _coerce_evaluate_result(raw)
            if last.get("ready") is True:
                return last
        except (RuntimeError, TimeoutError, OSError):
            pass
        if last.get("__windowHidden"):
            # Same offscreen-window fallback as wait_for_state: a hidden window
            # freezes React rendering on its skeleton, so restore before polling.
            _restore_e2e_window_via_cdp(page)
        time.sleep(0.5)
    return last


def _poke_chat_route_render(client: object, page: object, chat_id: str) -> None:
    client.evaluate(  # type: ignore[attr-defined]
        page,
        f"(async () => window.__MYRM_E2E_CHAT__?.pokeChatRouteRender?.({json.dumps(chat_id)}))()",
        timeout_sec=20.0,
    )


_SCROLL_MESSAGES_INTO_VIEW_JS = """(() => {
  const scrollEl = document.querySelector('.overflow-y-auto');
  if (scrollEl) {
    scrollEl.scrollTop = scrollEl.scrollHeight;
  }
  window.scrollTo(0, document.body.scrollHeight);
  return { ok: true, scrollHeight: scrollEl?.scrollHeight ?? 0 };
})()"""

_MEMORY_LIFECYCLE_PROBE_JS = """(async () => {
  const timeline = document.querySelector('[data-testid="memory-lifecycle-timeline"]');
  const retryBtn = timeline?.querySelector('button');
  const retryText = (retryBtn?.textContent || '').trim();
  // Must match a real rendered retry control — body.textContent also contains
  // next-intl bundles ("Retry extraction") and causes false positives.
  const hasRetry =
    !!retryBtn
    && /Retry extraction|重试提取|重試提取|Extraktion wiederholen|抽出を再試行|추출 재시도/i.test(
      retryText,
    );
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const path = location.pathname.replace(/^\\//, '');
  const lastMsg = msgs.length > 0 ? msgs[msgs.length - 1] : null;
  let traceCount = -1;
  let scopedEventCount = -1;
  let traceErr = '';
  try {
    const chatId = path;
    const res = await fetch(
      '/api/v1/statistics/session/' + encodeURIComponent(chatId) + '/trace',
      { credentials: 'include' },
    );
    const json = await res.json();
    const data = json.data ?? json;
    const events = Array.isArray(data.memory_events) ? data.memory_events : [];
    traceCount = events.length;
    const createdAtRaw = lastMsg?.createdAt;
    let messageCreatedAtMs = null;
    if (createdAtRaw instanceof Date) {
      messageCreatedAtMs = createdAtRaw.getTime();
    } else if (typeof createdAtRaw === 'string' || typeof createdAtRaw === 'number') {
      messageCreatedAtMs =
        typeof createdAtRaw === 'number' ? createdAtRaw : Date.parse(createdAtRaw);
    }
    if (messageCreatedAtMs != null && Number.isFinite(messageCreatedAtMs)) {
      scopedEventCount = events.filter(
        (event) => (Number(event.timestamp) * 1000) >= messageCreatedAtMs - 5000,
      ).length;
    } else {
      scopedEventCount = events.length;
    }
  } catch (err) {
    traceErr = String(err);
  }
  const createdAtRaw = lastMsg?.createdAt;
  let messageCreatedAtMs = null;
  if (createdAtRaw instanceof Date) {
    messageCreatedAtMs = createdAtRaw.getTime();
  } else if (typeof createdAtRaw === 'string' || typeof createdAtRaw === 'number') {
    messageCreatedAtMs =
      typeof createdAtRaw === 'number' ? createdAtRaw : Date.parse(createdAtRaw);
  }
  const trackWriteExtract =
    Boolean(store?.chatId)
    && lastMsg?.role === 'assistant'
    && !Boolean(store?.loading);
  return {
    ready: !!timeline && hasRetry,
    hasTimeline: !!timeline,
    hasRetry,
    onChat: path.startsWith('e2ememlife') || /^c-/.test(path),
    path: location.pathname,
    msgCount: msgs.length,
    msgDomCount: document.querySelectorAll('[data-message-id]').length,
    loading: Boolean(store?.loading),
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
    traceCount,
    scopedEventCount,
    traceErr,
    trackWriteExtract,
    messageCreatedAtMs,
    assistantContentHead: String(lastMsg?.content ?? '').slice(0, 120),
    visibility: document.visibilityState,
  };
})()"""


def _bridge_ready_timeout_sec() -> float:
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 180.0
    except ImportError:
        pass
    return 90.0


def _chat_ui_wait_timeout_sec(base: float = 60.0) -> float:
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return max(base, 120.0)
    except ImportError:
        pass
    return base


def _wait_orchestrator_lease_ready(*, timeout_sec: float = 120.0) -> None:
    """Wait until wave is open and MYRM_E2E_LEASE_ID is active (admit→pytest handoff race)."""
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    if not lease_id:
        return
    wave_sh = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "wave.sh"
    deadline = time.monotonic() + timeout_sec
    last_detail = "unknown"
    while time.monotonic() < deadline:
        try:
            proc = subprocess.run(
                ["bash", str(wave_sh), "status"],
                capture_output=True,
                text=True,
                timeout=15.0,
                check=False,
            )
            if proc.returncode == 0:
                payload = json.loads(proc.stdout)
                wave = payload.get("wave")
                wave_open = isinstance(wave, dict) and wave.get("status") == "open"
                active = payload.get("activeLeases")
                lease_active = isinstance(active, list) and any(
                    isinstance(item, dict)
                    and item.get("leaseId") == lease_id
                    and item.get("status") == "active"
                    for item in active
                )
                if wave_open and lease_active:
                    return
                last_detail = (
                    f"wave_open={wave_open} lease_active={lease_active} "
                    f"lease={lease_id[:8]}"
                )
        except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            last_detail = str(exc)
        time.sleep(2.0)
    raise RuntimeError(
        "E2E_ORCHESTRATOR_LEASE_DENIED: orchestrator lease not ready after "
        f"{timeout_sec}s ({last_detail})"
    )


def _force_mux_heal_before_retry() -> None:
    _wait_orchestrator_lease_ready(timeout_sec=120.0)
    _require_e2e_cdp_ready(budget_sec=45.0)
    try:
        from mux_attach_force_restart import force_mux_attach_restart_scoped

        force_mux_attach_restart_scoped(reason="memory lifecycle chrome outer retry")
    except RuntimeError as exc:
        if "MUX_ATTACH_RESTART_BLOCKED_PARALLEL" not in str(exc):
            raise
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text:
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _seed_memory_lifecycle_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json(
        "POST", f"{api_url}/api/v1/chats/test/seed-memory-lifecycle-fixture"
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    assert chat_id.startswith("e2ememlife")
    assert message_id
    _ensure_seeded_chat_ready(api_url, chat_id)
    return {"chat_id": chat_id, "message_id": message_id}


def _ensure_seeded_chat_ready(
    api_url: str,
    chat_id: str,
    *,
    timeout_sec: float = 45.0,
) -> None:
    """Poll private API before Chrome — parallel SHPOIB may restart backend briefly after seed."""
    deadline = time.monotonic() + timeout_sec
    last_error = "timeout"
    while time.monotonic() < deadline:
        try:
            payload = http_json(
                "GET",
                f"{api_url}/api/v1/chats/{chat_id}/messages",
            )
            messages: list[object] = []
            if isinstance(payload, dict):
                data = payload.get("data")
                if isinstance(data, dict) and isinstance(data.get("messages"), list):
                    messages = data["messages"]
                elif isinstance(payload.get("messages"), list):
                    messages = payload["messages"]
            has_assistant = any(
                isinstance(msg, dict) and msg.get("role") == "assistant"
                for msg in messages
            )
            if len(messages) >= 2 and has_assistant:
                return
            last_error = (
                f"messages not ready; count={len(messages)} assistant={has_assistant}"
            )
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise AssertionError(
        f"Memory lifecycle seed chat not readable on {api_url}: {last_error}"
    )


def _run_lifecycle_assertions(
    api_url: str, ui_url: str, *, warm_route: bool = True
) -> None:
    seeded = _seed_memory_lifecycle_fixture(api_url)
    chat_id = seeded["chat_id"]
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    home_url = f"{ui_url.rstrip('/')}/"
    ui_wait_sec = _chat_ui_wait_timeout_sec(90.0)
    attach_wait_sec = max(45.0, min(_attach_eval_timeout_sec(), 120.0))

    if warm_route:
        warm_ui_route("/")
        warm_ui_route(f"/{chat_id}")

    with open_mcp_page(home_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=home_url)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        _ensure_react_bridge_on_home(client, page, ui_url=ui_url)

        client.navigate(page, chat_url)  # type: ignore[attr-defined]
        time.sleep(1.5)
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        attached = _await_attach_memory_chat(
            client,
            page,
            chat_id,
            timeout_sec=attach_wait_sec,
            ui_url=ui_url,
        )
        assert attached.get("ok") is True, json.dumps(attached, ensure_ascii=False)

        dismiss_blocking_modals(client, page, recover_url=chat_url)
        _poke_chat_route_render(client, page, chat_id)

        chat_ui_probe = _probe_chat_ui_state(
            client, page, timeout_sec=min(45.0, ui_wait_sec * 0.5)
        )
        if (
            chat_ui_probe.get("ready") is not True
            and chat_ui_probe.get("hasMessageListSkeleton") is True
        ):
            reload_mcp_page(client, page, target_url=chat_url, timeout_ms=120_000)
            dismiss_blocking_modals(client, page, recover_url=chat_url)
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            attached = _await_attach_memory_chat(
                client,
                page,
                chat_id,
                timeout_sec=attach_wait_sec,
                ui_url=ui_url,
            )
            assert attached.get("ok") is True, attached
            _poke_chat_route_render(client, page, chat_id)
        elif chat_ui_probe.get("ready") is not True:
            client.navigate(page, home_url)  # type: ignore[attr-defined]
            time.sleep(1.5)
            _ensure_react_bridge_on_home(client, page, ui_url=ui_url)
            client.navigate(page, chat_url)  # type: ignore[attr-defined]
            time.sleep(1.5)
            dismiss_blocking_modals(client, page, recover_url=chat_url)
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            attached = _await_attach_memory_chat(
                client,
                page,
                chat_id,
                timeout_sec=attach_wait_sec,
                ui_url=ui_url,
            )
            assert attached.get("ok") is True, attached
            _poke_chat_route_render(client, page, chat_id)

        route_ready = wait_for_state(
            client,
            page,
            _ROUTE_SEGMENT_CLEARED_JS,
            timeout_sec=30.0,
            page_url=chat_url,
        )
        assert route_ready.get("ready") is True, route_ready

        hydrated = wait_for_state(
            client,
            page,
            _CHAT_HYDRATED_JS,
            timeout_sec=_chat_ui_wait_timeout_sec(45.0),
            page_url=chat_url,
        )
        assert hydrated.get("ready") is True, hydrated

        chat_ui_probe = wait_for_state(
            client,
            page,
            _CHAT_UI_READY_JS,
            timeout_sec=ui_wait_sec,
            page_url=chat_url,
        )
        assert chat_ui_probe.get("ready") is True, json.dumps(
            chat_ui_probe, ensure_ascii=False
        )

        client.evaluate(page, _SCROLL_MESSAGES_INTO_VIEW_JS, timeout_sec=15.0)
        _poke_chat_route_render(client, page, chat_id)
        time.sleep(1.5)

        state = wait_for_state(
            client,
            page,
            _MEMORY_LIFECYCLE_PROBE_JS,
            timeout_sec=_chat_ui_wait_timeout_sec(90.0),
            page_url=chat_url,
        )
        assert state.get("ready") is True, json.dumps(
            state, indent=2, ensure_ascii=False
        )
        assert state.get("hasTimeline") is True
        assert state.get("hasRetry") is True


def _run_with_transport_retry(
    runner: Callable[..., None],
    api_url: str,
    ui_url: str,
) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resolved_api = get_e2e_api_url()
            runner(resolved_api, ui_url, warm_route=(attempt == 1))
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_memory_lifecycle_timeline_and_retry() -> None:
    """Seeded ledger extract error must render lifecycle strip + retry on last assistant message."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_lifecycle_assertions, api_url, ui_url)
