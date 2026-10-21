"""Real Chrome + live API integration test for the Postiz catalog entry.

Covers the remote-entry connect chain:
1. Live catalog API returns the postiz entry (social category, hosted MCP,
   bearer API-key auth) and Chinese keyword search surfaces it.
2. In the Service Directory UI, connecting a remote hosted entry must skip
   the localhost connectivity probe entirely and go straight to the
   security-gate scan/verify handshake; a bad API key must fail there
   without saving the config.
"""

from __future__ import annotations

import time
import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
    warm_ui_route,
)


def _is_retryable_open_mcp_error(exc: RuntimeError) -> bool:
    message = str(exc)
    if "No McpPage found for the given page" in message:
        return True
    if "SHPOIB runtime rebind after reload failed" in message:
        return True
    if "pageId " in message and "not owned by this shim session" in message:
        return True
    if "Chrome MCP new_page failed: Error: Timed out after waiting 30000ms" in message:
        return True
    return False


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_postiz_remote_entry_skips_probe_and_reaches_security_gate() -> None:
    api_url = get_e2e_api_url()

    # 1) Live API: the postiz entry is served with the remote hosted-MCP contract.
    detail = http_json("GET", f"{api_url}/api/v1/integrations/catalog/postiz")
    assert isinstance(detail, dict)
    assert detail.get("success") is True
    entry = detail.get("data")
    assert isinstance(entry, dict)
    assert entry.get("category") == "social"
    assert entry.get("connectorType") == "mcp"
    assert entry.get("authType") == "bearer"
    mcp_cfg = entry.get("mcpConfig")
    assert isinstance(mcp_cfg, dict)
    assert mcp_cfg.get("type") == "streamable_http"
    assert mcp_cfg.get("url") == "https://mcp.postiz.com/mcp"

    # Chinese discoverability through the live search chain.
    for query in ("排期", "postiz"):
        encoded = urllib.parse.quote(query)
        search = http_json("GET", f"{api_url}/api/v1/integrations/catalog?q={encoded}")
        assert isinstance(search, dict)
        payload = search.get("data")
        assert isinstance(payload, dict)
        ids = {e.get("id") for e in payload.get("entries", []) if isinstance(e, dict)}
        assert "postiz" in ids, f"search '{query}' must return postiz, got {ids}"

    # 2) Real Chrome UI chain: remote entries skip the localhost probe and
    # reach the security gate; a bad key fails there without being saved.
    warm_ui_route("/settings/integrationCatalog")
    last_open_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            with open_settings_subroute("/settings/integrationCatalog", timeout_ms=90_000) as (client, page):
                # The card only renders after the async catalog fetch resolves. Wait on
                # it with the page URL so ``wait_for_state`` can run its documented
                # blank/deferred heal if parallel load strands the settings skeleton,
                # and before the fetch spy is installed so a heal reload cannot wipe it.
                card_ready = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4'));
                      return { ready: titles.some((el) => /Postiz/i.test(el.textContent || '')) };
                    })()""",
                    timeout_sec=60.0,
                    page_url=f"{get_e2e_ui_url().rstrip('/')}/settings/integrationCatalog",
                )
                assert card_ready.get("ready") is True, f"Postiz card never rendered: {card_ready}"

                fetch_spy = client.evaluate(
                    page,
                    """(() => {
                      if (!window.__integrationFetchLogs) {
                        window.__integrationFetchLogs = [];
                        const origFetch = window.fetch.bind(window);
                        window.fetch = async (...args) => {
                          const req = args[0];
                          const init = args[1] || {};
                          const url = typeof req === 'string' ? req : req?.url;
                          const method = (init.method || req?.method || 'GET').toUpperCase();
                          const resp = await origFetch(...args);
                          let body = null;
                          try {
                            body = await resp.clone().json();
                          } catch (_err) {
                            body = null;
                          }
                          window.__integrationFetchLogs.push({
                            url: String(url || ''),
                            method,
                            status: resp.status,
                            body,
                          });
                          return resp;
                        };
                      }
                      return { ready: true };
                    })()""",
                    timeout_sec=8.0,
                )
                assert isinstance(fetch_spy, dict)
                assert fetch_spy.get("ready") is True
                open_dialog = client.evaluate(
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4'));
                      const title = titles.find((el) => /Postiz/i.test(el.textContent || ''));
                      if (!title) return { ready: false, reason: 'entry_missing' };
                      const card = title.closest('div');
                      if (!card) return { ready: false, reason: 'card_missing' };
                      const button = Array.from(card.querySelectorAll('button')).find((el) =>
                        /Connect|连接/i.test(el.textContent || '')
                      );
                      if (!button) return { ready: false, reason: 'card_connect_missing' };
                      button.click();
                      return { ready: true };
                    })()""",
                    timeout_sec=8.0,
                )
                assert isinstance(open_dialog, dict)
                assert open_dialog.get("ready") is True, f"failed to open dialog: {open_dialog}"

                fill_key = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const dialog = document.querySelector('[role="dialog"]');
                      if (!dialog) return { ready: false, reason: 'dialog_missing' };
                      const input = dialog.querySelector('input');
                      if (!input) return { ready: false, reason: 'credential_input_missing' };
                      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                      setter.call(input, 'e2e-invalid-postiz-key');
                      input.dispatchEvent(new Event('input', { bubbles: true }));
                      input.dispatchEvent(new Event('change', { bubbles: true }));
                      return { ready: true };
                    })()""",
                    timeout_sec=30.0,
                )
                assert fill_key.get("ready") is True, f"failed to fill API key: {fill_key}"

                click_connect = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const dialog = document.querySelector('[role="dialog"]');
                      if (!dialog) return { ready: false };
                      const button = Array.from(dialog.querySelectorAll('button')).find((el) =>
                        /Connect|连接/i.test(el.textContent || '') && !el.disabled
                      );
                      if (!button) return { ready: false, reason: 'dialog_connect_missing' };
                      button.click();
                      return { ready: true };
                    })()""",
                    timeout_sec=30.0,
                )
                assert click_connect.get("ready") is True

                fetch_chain = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const logs = Array.isArray(window.__integrationFetchLogs) ? window.__integrationFetchLogs : [];
                      const probeCalls = logs.filter((item) => item.url.includes('/api/v1/integrations/mcp/probe'));
                      const scanCalls = logs.filter((item) => item.url.includes('/api/v1/integrations/mcp/scan'));
                      const verifyCalls = logs.filter((item) => item.url.includes('/api/v1/integrations/mcp/verify'));
                      return {
                        ready: scanCalls.length > 0 || verifyCalls.length > 0,
                        probeCalls: probeCalls.length,
                        scanSeen: scanCalls.length > 0,
                        verifySeen: verifyCalls.length > 0,
                      };
                    })()""",
                    timeout_sec=60.0,
                )
                assert fetch_chain.get("ready") is True, f"security gate never reached: {fetch_chain}"
                assert fetch_chain.get("probeCalls") == 0, f"remote entry must skip localhost probe: {fetch_chain}"
                assert fetch_chain.get("scanSeen") is True or fetch_chain.get("verifySeen") is True

                # The bad key must not result in a saved/enabled Postiz config:
                # after the gate settles, the card still offers Connect.
                card_state = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4'));
                      const title = titles.find((el) => /Postiz/i.test(el.textContent || ''));
                      if (!title) return { ready: false, reason: 'entry_missing' };
                      const card = title.closest('div');
                      if (!card) return { ready: false, reason: 'card_missing' };
                      const text = card.textContent || '';
                      const buttons = Array.from(card.querySelectorAll('button')).map((el) => el.textContent || '');
                      return {
                        ready: true,
                        hasConnectButton: buttons.some((t) => /Connect|连接/i.test(t)),
                        showsConnected: /Connected|已连接/i.test(text) && !buttons.some((t) => /Connect|连接/i.test(t)),
                      };
                    })()""",
                    timeout_sec=30.0,
                )
                assert card_state.get("hasConnectButton") is True, f"bad key must not save config: {card_state}"
                assert card_state.get("showsConnected") is not True
            break
        except RuntimeError as exc:
            last_open_error = exc
            if not _is_retryable_open_mcp_error(exc) or attempt == 2:
                raise
            time.sleep(2.0)
    else:
        raise AssertionError(f"failed to open MCP page after retries: {last_open_error}")
