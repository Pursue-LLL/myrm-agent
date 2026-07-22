"""Real Chrome MCP E2E for render_ui surface gate UX (Web-only hint + client_surface hook)."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import wait_e2e_provider_ready  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)

_FETCH_HOOK_JS = """(() => {
  window.__MYRM_CLIENT_SURFACE_CAPTURE__ = [];
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    try {
      const input = args[0];
      const url = typeof input === 'string' ? input : input?.url || '';
      if (url.includes('/agents/agent-stream')) {
        const init = args[1];
        const rawBody = init && typeof init === 'object' ? init.body : null;
        if (typeof rawBody === 'string' && rawBody.trim()) {
          const parsed = JSON.parse(rawBody);
          window.__MYRM_CLIENT_SURFACE_CAPTURE__.push(parsed.client_surface ?? parsed.clientSurface ?? null);
        }
      }
    } catch {
      // capture failures fail closed in assertion
    }
    return response;
  };
  return { hooked: true };
})()"""

_AGENT_EDITOR_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-testid="app-layout"]') &&
    !!document.querySelector('[data-testid="agent-tab-capabilities"]'),
  url: location.href,
}))()"""

_CLICK_CAPABILITIES_JS = """(() => {
  const capTab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  if (capTab && capTab.getAttribute('aria-selected') !== 'true') {
    capTab.click();
  }
  return { clicked: true };
})()"""

_OPEN_BUILTIN_DIALOG_JS = """(() => {
  const builtinCard = Array.from(document.querySelectorAll('button')).find((btn) =>
    /Built-in Tools|内置工具/i.test(btn.textContent || ''),
  );
  if (!builtinCard) {
    return { clicked: false };
  }
  builtinCard.click();
  return { clicked: true };
})()"""

_BUILTIN_DIALOG_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[role="dialog"]') &&
    !!document.querySelector('[data-testid="builtin-render_ui"]'),
}))()"""

_TOGGLE_RENDER_UI_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-render_ui"]');
  if (!card) {
    return { toggled: false, reason: 'missing-card' };
  }
  card.click();
  const checkedMarker = card.querySelector('svg path[d="M1 4L3.5 6.5L9 1"]');
  if (checkedMarker) {
    return { toggled: true, wasChecked: true };
  }
  return { toggled: true, wasChecked: false };
})()"""

_HINT_ASSERT_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    hasHint:
      /Web Chat and the desktop app|Web 对话与桌面客户端/i.test(text) &&
      /Telegram|定时任务|scheduled tasks/i.test(text),
  };
})()"""

_BRIDGE_READY_JS = """(() => ({
  ready: typeof window.__MYRM_E2E_CHAT__?.handleSubmit === 'function',
}))()"""

_WAIT_SEND_READY_JS = """(() => {
  return (async () => {
    const bridge = window.__MYRM_E2E_CHAT__;
    if (!bridge?.ensureProviders) {
      return { ready: false, err: 'no-bridge' };
    }
    await bridge.ensureProviders();
    const deadline = Date.now() + 60000;
    while (Date.now() < deadline) {
      if (bridge.isSendReady?.()) {
        return { ready: true };
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return { ready: false, debug: bridge.debugProviderState?.() };
  })();
})()"""

_SUBMIT_VIA_BRIDGE_JS = """(() => {
  return (async () => {
    const bridge = window.__MYRM_E2E_CHAT__;
    if (!bridge) {
      return { ok: false, err: 'no-bridge' };
    }
    await bridge.ensureProviders?.();
    bridge.setInputMessage?.('surface gate e2e ping');
    await bridge.handleSubmit?.();
    return bridge.lastSubmitResult ?? { ok: false, err: 'no-result' };
  })();
})()"""

_CAPTURE_ASSERT_JS = """(() => {
  const capture = window.__MYRM_CLIENT_SURFACE_CAPTURE__ || [];
  const lastSurface = capture.length ? capture[capture.length - 1] : null;
  return {
    ready: capture.length >= 1,
    captureLen: capture.length,
    lastSurface,
  };
})()"""

_CAPTURE_TAURI_ASSERT_JS = """(() => {
  const capture = window.__MYRM_CLIENT_SURFACE_CAPTURE__ || [];
  const lastSurface = capture.length ? capture[capture.length - 1] : null;
  return {
    ready: lastSurface === 'tauri',
    captureLen: capture.length,
    lastSurface,
  };
})()"""

_SIMULATE_TAURI_RUNTIME_JS = """(() => {
  window.__TAURI__ = window.__TAURI__ ?? { __e2e: true };
  return {
    isTauri: '__TAURI__' in window,
    host: location.hostname,
  };
})()"""

_CLEAR_SURFACE_CAPTURE_JS = """(() => {
  window.__MYRM_CLIENT_SURFACE_CAPTURE__ = [];
  return { cleared: true };
})()"""

_SUBMIT_TAURI_SURFACE_JS = """(() => {
  return (async () => {
    const bridge = window.__MYRM_E2E_CHAT__;
    if (!bridge) {
      return { ok: false, err: 'no-bridge' };
    }
    await bridge.ensureProviders?.();
    bridge.setInputMessage?.('tauri surface gate e2e ping');
    await bridge.handleSubmit?.();
    return bridge.lastSubmitResult ?? { ok: false, err: 'no-result' };
  })();
})()"""


def _create_editable_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Surface Gate E2E {suffix}",
        "description": "Chrome E2E for render_ui surface hint",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search"],
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = (
        created.get("data", {}).get("id")
        if isinstance(created.get("data"), dict)
        else created.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _submit_and_wait_client_surface(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    submit_js: str,
    capture_js: str,
    expected_surfaces: frozenset[str],
    failure_label: str,
    max_attempts: int = 3,
    capture_timeout_sec: float = 120.0,
) -> dict[str, object]:
    """Submit chat and wait for client_surface capture; retry after mux contention."""
    last_capture: dict[str, object] = {}
    last_submit: dict[str, object] = {}
    for attempt in range(max_attempts):
        client.evaluate(page, _CLEAR_SURFACE_CAPTURE_JS, timeout_sec=5.0)
        wait_for_state(client, page, _WAIT_SEND_READY_JS, timeout_sec=90.0)
        raw_submit = client.evaluate(page, submit_js, timeout_sec=120.0)
        last_submit = (
            raw_submit if isinstance(raw_submit, dict) else {"value": raw_submit}
        )
        assert (
            last_submit.get("ok") is True
        ), f"{failure_label} submit failed (attempt {attempt + 1}/{max_attempts}): {last_submit}"
        try:
            last_capture = wait_for_state(
                client,
                page,
                capture_js,
                timeout_sec=capture_timeout_sec,
            )
            if last_capture.get("lastSurface") in expected_surfaces:
                return last_capture
        except AssertionError:
            if attempt >= max_attempts - 1:
                raise AssertionError(
                    f"{failure_label} capture failed (attempt {attempt + 1}/{max_attempts}): "
                    f"submit={last_submit}; capture={last_capture}"
                ) from None
            time.sleep(2.0 * (attempt + 1))
    raise AssertionError(
        f"{failure_label} failed after retries: submit={last_submit}; capture={last_capture}"
    )


def _submit_and_wait_web_surface(
    client: ChromeMcpClient,
    page: McpPage,
) -> dict[str, object]:
    return _submit_and_wait_client_surface(
        client,
        page,
        submit_js=_SUBMIT_VIA_BRIDGE_JS,
        capture_js=_CAPTURE_ASSERT_JS,
        expected_surfaces=frozenset({"web", "tauri"}),
        failure_label="client_surface",
    )


def _submit_and_wait_tauri_surface(
    client: ChromeMcpClient,
    page: McpPage,
) -> dict[str, object]:
    return _submit_and_wait_client_surface(
        client,
        page,
        submit_js=_SUBMIT_TAURI_SURFACE_JS,
        capture_js=_CAPTURE_TAURI_ASSERT_JS,
        expected_surfaces=frozenset({"tauri"}),
        failure_label="client_surface=tauri",
    )


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json(
            "DELETE",
            f"{api_url}/api/v1/user-agents/{agent_id}",
            expected_statuses=frozenset({200, 204}),
        )
    except RuntimeError:
        pass


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_render_ui_surface_hint_and_client_surface_in_real_ui() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    agent_id = _create_editable_agent(api_url)
    agent_settings_url = f"{ui_url}/settings/agents?agentId={agent_id}"

    try:
        with open_mcp_page(agent_settings_url, timeout_ms=120_000) as (client, page):
            wait_for_state(client, page, _AGENT_EDITOR_READY_JS, timeout_sec=90.0)
            client.evaluate(page, _CLICK_CAPABILITIES_JS, timeout_sec=10.0)
            wait_for_state(
                client,
                page,
                """(() => ({
                  ready: /Built-in Tools|内置工具/i.test(document.body?.innerText || ''),
                }))()""",
                timeout_sec=30.0,
            )
            opened = client.evaluate(page, _OPEN_BUILTIN_DIALOG_JS, timeout_sec=15.0)
            assert isinstance(opened, dict)
            assert (
                opened.get("clicked") is True
            ), f"Built-in Tools card not found: {opened}"

            wait_for_state(client, page, _BUILTIN_DIALOG_READY_JS, timeout_sec=30.0)
            client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
            toggled = client.evaluate(page, _TOGGLE_RENDER_UI_JS, timeout_sec=15.0)
            assert isinstance(toggled, dict)
            assert (
                toggled.get("toggled") is True
            ), f"Failed to toggle render_ui: {toggled}"

            hint = client.evaluate(page, _HINT_ASSERT_JS, timeout_sec=10.0)
            assert isinstance(hint, dict)
            assert (
                hint.get("hasHint") is True
            ), f"Missing renderUiWebOnlyHint in UI: {hint}"

        if not wait_e2e_provider_ready():
            pytest.fail(
                "Provider config not ready for client_surface capture — run via ./myrm test -m chrome_e2e "
                "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)",
            )

        with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
            wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)
            client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
            capture = _submit_and_wait_web_surface(client, page)
            assert capture.get("lastSurface") in {
                "web",
                "tauri",
            }, f"Unexpected client_surface: {capture.get('lastSurface')}"
    finally:
        _delete_agent(api_url, agent_id)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_client_surface_emits_tauri_when_tauri_runtime_simulated() -> None:
    """Chrome READ: injecting window.__TAURI__ must send client_surface=tauri on agent-stream."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for tauri client_surface capture — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome",
        )

    ui_url = get_e2e_ui_url()
    with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)
        client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        simulated = client.evaluate(page, _SIMULATE_TAURI_RUNTIME_JS, timeout_sec=10.0)
        assert isinstance(simulated, dict)
        assert (
            simulated.get("isTauri") is True
        ), f"Tauri runtime simulation failed: {simulated}"

        capture = _submit_and_wait_tauri_surface(client, page)
        assert capture.get("lastSurface") == "tauri"
