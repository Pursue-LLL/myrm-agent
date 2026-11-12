"""Chat page helpers: route readiness, agent binding, the security preset trigger and the send-idle wait."""

from __future__ import annotations

import json
import time

from cdp_chat.support import get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from .parallel_load import _parallel_chrome_e2e_active
from .reload import reload_mcp_page
from .wait_state import wait_for_state


def chat_agent_binding_probe_js(*, expected_preset: str, agent_id: str | None = None) -> str:
    """Store probe aligned with frontend sessionAgentHydration.isAgentSessionHydrated SSOT."""
    expected_json = json.dumps(expected_preset)
    agent_json = json.dumps(agent_id) if agent_id else "null"
    return f"""(() => {{
  const store = window.__myrmChatStore?.getState?.();
  if (!store) return {{ ready: false, err: 'no-store' }};
  const preset = store.securityPreset;
  const boundAgentId = store.agentConfig?.agentId ?? null;
  const ready = preset === {expected_json}
    && ({agent_json} === null || boundAgentId === {agent_json})
    && store.isMessagesLoaded === true
    && store.loading !== true;
  return {{
    ready,
    preset,
    expected: {expected_json},
    boundAgentId,
    expectedAgentId: {agent_json},
    actionMode: store.actionMode ?? null,
    isMessagesLoaded: store.isMessagesLoaded ?? false,
    loading: store.loading ?? null,
    apiBase: window.__MYRM_E2E_API_BASE__ ?? window.__MYRM_E2E_RUNTIME__?.apiBase ?? null,
    err: null,
  }};
}})()"""


_SECURITY_PRESET_TRIGGER_PROBE_JS = """(() => {
  const trigger = document.querySelector('[data-testid="security-preset-trigger"]');
  return { ready: !!trigger, hasTrigger: !!trigger };
})()"""


def wait_for_security_preset_trigger(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 30.0,
) -> dict[str, object]:
    """Wait for SecurityPresetSelector trigger DOM under parallel turbopack load."""
    if _parallel_chrome_e2e_active():
        timeout_sec = max(timeout_sec, 60.0)
    state = wait_for_state(client, page, _SECURITY_PRESET_TRIGGER_PROBE_JS, timeout_sec=timeout_sec)
    if state.get("ready") is not True:
        raise AssertionError(f"Security preset trigger not ready: {json.dumps(state, ensure_ascii=False)}")
    return state


def attach_chat_and_wait_agent_binding(
    client: ChromeMcpClient,
    page: McpPage,
    chat_id: str,
    *,
    expected_preset: str,
    agent_id: str,
    timeout_sec: float = 90.0,
) -> dict[str, object]:
    """Deterministic agent+preset hydrate via E2E bridge attachToChat."""
    if _parallel_chrome_e2e_active():
        timeout_sec = max(timeout_sec, 120.0)
    chat_id_json = json.dumps(chat_id)
    agent_json = json.dumps(agent_id)
    expected_json = json.dumps(expected_preset)
    attach_js = f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  const store = window.__myrmChatStore?.getState?.();
  if (
    store?.agentConfig?.agentId === {agent_json}
    && store?.securityPreset === {expected_json}
    && store?.chatId === {chat_id_json}
    && store?.isMessagesLoaded
    && store?.loading !== true
  ) {{
    return {{ ok: true, skipped: true }};
  }}
  try {{
    await bridge.attachToChat({chat_id_json});
    return {{ ok: true, skipped: false }};
  }} catch (err) {{
    return {{ ok: false, err: String(err) }};
  }}
}})()"""
    attach_result = client.evaluate(page, attach_js, timeout_sec=min(120.0, timeout_sec))
    if not isinstance(attach_result, dict) or attach_result.get("ok") is not True:
        raise AssertionError(f"attachToChat failed: {attach_result!r}")
    probe = chat_agent_binding_probe_js(expected_preset=expected_preset, agent_id=agent_id)
    state = wait_for_state(client, page, probe, timeout_sec=timeout_sec)
    if state.get("ready") is not True:
        raise AssertionError(f"Agent binding not ready: {json.dumps(state, ensure_ascii=False)}")
    return state


CHAT_ROUTE_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="app-layout"]'),
  href: location.href,
}))()"""

_CHAT_HYDRATION_JS = """(() => ({
  hasInput: !!document.querySelector('[data-chat-input]'),
  msgs: (window.__myrmChatStore?.getState?.()?.messages || []).length,
  bodyLen: (document.body?.innerText || '').trim().length,
  errorOverlay: !!document.querySelector('nextjs-portal, nextjs-error-overlay'),
}))()"""

_CURRENT_HREF_JS = "location.href"


def ensure_chat_route(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    target_url: str,
    timeout_ms: int = 180_000,
) -> None:
    """Force ``page`` onto ``target_url`` and verify React hydration.

    Reused warm shells may bind a tab owned by another isolated runtime (stale
    origin/route) or reach the URL while React is still suspended (SSR shell
    only). Once the target route is reached, the chat input must be present and
    free of a dev error overlay; otherwise the page is reloaded cache-bypassing
    (about:blank → target) so the full, freshly compiled client bundle mounts.
    A plain ``window.location.href`` navigation keeps serving stale Turbopack
    chunks and re-triggers ``ChunkLoadError`` under shared dev hot reload.
    """
    target_suffix = target_url.rstrip("/")
    deadline = time.monotonic() + timeout_ms / 1000.0
    hard_navigations = 0
    while time.monotonic() < deadline:
        try:
            current = client.evaluate(page, _CURRENT_HREF_JS, timeout_sec=5.0)
        except (RuntimeError, TimeoutError, OSError):
            current = None
        if isinstance(current, str) and current.rstrip("/").endswith(target_suffix):
            try:
                hydrated = client.evaluate(page, _CHAT_HYDRATION_JS, timeout_sec=10.0)
            except (RuntimeError, TimeoutError, OSError):
                hydrated = None
            if isinstance(hydrated, dict) and (
                (hydrated.get("hasInput") is True and hydrated.get("errorOverlay") is not True)
                or int(hydrated.get("msgs") or 0) > 0
            ):
                return
            if hard_navigations < 3:
                hard_navigations += 1
                try:
                    reload_mcp_page(
                        client,
                        page,
                        target_url=target_url,
                        timeout_ms=min(90_000, timeout_ms),
                        ignore_cache=True,
                    )
                except (RuntimeError, TimeoutError, OSError):
                    pass
                time.sleep(4.0)
                continue
            break
        try:
            client.navigate(page, target_url, timeout_ms=timeout_ms)
        except (RuntimeError, TimeoutError, OSError):
            pass
        time.sleep(2.0)
        try:
            current = client.evaluate(page, _CURRENT_HREF_JS, timeout_sec=5.0)
        except (RuntimeError, TimeoutError, OSError):
            current = None
        if isinstance(current, str) and current.rstrip("/").endswith(target_suffix):
            continue
        try:
            reload_mcp_page(
                client,
                page,
                target_url=target_url,
                timeout_ms=min(90_000, timeout_ms),
                ignore_cache=True,
            )
        except (RuntimeError, TimeoutError, OSError):
            pass
        time.sleep(3.0)
    route = wait_for_state(
        client,
        page,
        CHAT_ROUTE_READY_JS,
        timeout_sec=min(60.0, max(5.0, deadline - time.monotonic())),
        page_url=target_url,
    )
    assert route.get("ready") is True, json.dumps(route, ensure_ascii=False)
    assert str(route.get("href") or "").startswith(get_e2e_ui_url().rstrip("/")), json.dumps(route, ensure_ascii=False)


_WAIT_CHAT_SEND_IDLE_JS = """(() => ({
  isStreaming: window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.isStreaming === true,
}))()"""


def wait_for_chat_send_idle(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 120.0,
) -> None:
    """Wait until chat store loading clears so sendWorkflowTemplateRun is not busy."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        touch_wall_progress(current_node="wait_for_chat_send_idle")
        try:
            raw = client.evaluate(
                page,
                _WAIT_CHAT_SEND_IDLE_JS,
                timeout_sec=min(15.0, max(5.0, deadline - time.monotonic())),
            )
        except (RuntimeError, TimeoutError, OSError):
            time.sleep(1.0)
            continue
        if isinstance(raw, dict) and raw.get("isStreaming") is not True:
            return
        time.sleep(1.0)
    raise AssertionError(f"Chat send path still busy after {timeout_sec}s (submitWorkflowTemplateRun loading gate)")
