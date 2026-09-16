"""Real Chrome MCP E2E: agent-stream must report the originating client_surface.

Covers the live `client_surface` contract (`web` from a browser, `tauri` when the
Tauri runtime is present) that downstream surface-dependent tooling relies on.
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    _warm_ui_parallel_wait_sec,
    get_e2e_ui_url,
    open_mcp_page,
    wait_e2e_provider_ready,
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
    bridge.setInputMessage?.('client surface e2e ping');
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
    bridge.setInputMessage?.('tauri surface e2e ping');
    await bridge.handleSubmit?.();
    return bridge.lastSubmitResult ?? { ok: false, err: 'no-result' };
  })();
})()"""


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


def _fail_if_provider_not_ready(context: str) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            f"Provider config not ready for {context} client_surface capture — run via "
            "./myrm test -m chrome_e2e after ./myrm ready --chrome "
            "(API /api/v1/config/readiness provider.is_ready must be true)",
        )


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_client_surface_emits_web_in_real_ui() -> None:
    _fail_if_provider_not_ready("web")

    ui_url = get_e2e_ui_url()
    with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
        wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        capture = _submit_and_wait_web_surface(client, page)
        assert capture.get("lastSurface") in {
            "web",
            "tauri",
        }, f"Unexpected client_surface: {capture.get('lastSurface')}"


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_client_surface_emits_tauri_when_tauri_runtime_simulated() -> None:
    """Chrome READ: injecting window.__TAURI__ must send client_surface=tauri on agent-stream."""
    _fail_if_provider_not_ready("tauri")

    ui_url = get_e2e_ui_url()
    with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
        wait_for_state(
            client,
            page,
            _BRIDGE_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        simulated = client.evaluate(page, _SIMULATE_TAURI_RUNTIME_JS, timeout_sec=10.0)
        assert isinstance(simulated, dict)
        assert (
            simulated.get("isTauri") is True
        ), f"Tauri runtime simulation failed: {simulated}"

        capture = _submit_and_wait_tauri_surface(client, page)
        assert capture.get("lastSurface") == "tauri"
