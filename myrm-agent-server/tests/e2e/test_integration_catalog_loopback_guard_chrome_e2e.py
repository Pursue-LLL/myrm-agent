"""Real Chrome + live API integration test for catalog loopback guard flow."""

from __future__ import annotations

import http.server
import os
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)


@contextmanager
def _temporary_loopback_server(port: int) -> Iterator[None]:
    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # noqa: D401
            return

    server = socketserver.TCPServer(("127.0.0.1", port), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()


@contextmanager
def _temporary_self_signed_tls_server() -> Iterator[str]:
    class _QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # noqa: D401
            return

    with tempfile.TemporaryDirectory(prefix="myrm-tls-probe-") as temp_dir:
        cert_path = os.path.join(temp_dir, "cert.pem")
        key_path = os.path.join(temp_dir, "key.pem")
        subprocess.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-keyout",
                key_path,
                "-out",
                cert_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        server = socketserver.TCPServer(("127.0.0.1", 0), _QuietHandler)
        tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls_context.load_cert_chain(certfile=cert_path, keyfile=key_path)
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = int(server.server_address[1])
            yield f"https://127.0.0.1:{port}"
        finally:
            server.shutdown()
            server.server_close()


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


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_integration_catalog_loopback_guard_end_to_end() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    # 1) Verify catalog scope semantics are explicit in live API.
    detail = http_json("GET", f"{api_url}/api/v1/integrations/catalog/unreal-engine")
    assert isinstance(detail, dict)
    assert detail.get("success") is True
    entry = detail.get("data")
    assert isinstance(entry, dict)
    assert entry.get("deploymentScope") == "local_tauri_only"
    mcp_cfg = entry.get("mcpConfig")
    assert isinstance(mcp_cfg, dict)
    assert mcp_cfg.get("deploymentScope") == "local_tauri_only"

    # 2) Probe endpoint real-chain checks (normal / failure / boundary).
    with _temporary_loopback_server(18081):
        reachable = http_json(
            "POST",
            f"{api_url}/api/v1/integrations/mcp/probe",
            {"url": "http://127.0.0.1:18081", "timeout": 3},
        )
    assert isinstance(reachable, dict)
    reachable_data = reachable.get("data")
    assert isinstance(reachable_data, dict)
    assert reachable_data.get("status") == "reachable"
    assert reachable_data.get("reasonCode") == "reachable"
    assert reachable_data.get("shouldBlockConnect") is False

    unreachable = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/mcp/probe",
        {"url": "http://127.0.0.1:18082", "timeout": 3},
    )
    assert isinstance(unreachable, dict)
    unreachable_data = unreachable.get("data")
    assert isinstance(unreachable_data, dict)
    assert unreachable_data.get("status") == "unreachable"
    assert unreachable_data.get("reasonCode") == "connection_refused"
    assert unreachable_data.get("shouldBlockConnect") is True

    boundary = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/mcp/probe",
        {"url": "http://example.com:8000/mcp", "timeout": 3},
        expected_statuses=frozenset({400}),
    )
    assert isinstance(boundary, dict)
    detail_payload = boundary.get("detail")
    assert isinstance(detail_payload, dict)
    assert "localhost addresses only" in str(detail_payload.get("message") or "")

    # 3) Real user flow in Service Directory UI (Chrome MCP mux).
    # For local-only entries, probe must gate the connect chain before scan/verify when
    # the editor MCP endpoint is not running.
    warm_ui_route("/settings/integrationCatalog")
    last_open_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            with open_mcp_page(f"{ui_url}/settings/integrationCatalog", timeout_ms=90_000) as (client, page):
                # Install fetch logger once to capture actual connect-chain network calls.
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

                # Click Unreal card's connect button, then confirm connect in dialog.
                open_dialog = client.evaluate(
                    page,
                    """(() => {
                      const titles = Array.from(document.querySelectorAll('h4'));
                      const title = titles.find((el) => /Unreal Engine|虚幻引擎/i.test(el.textContent || ''));
                      if (!title) return { ok: false, reason: 'entry_missing' };
                      const card = title.closest('div');
                      if (!card) return { ok: false, reason: 'card_missing' };
                      const button = Array.from(card.querySelectorAll('button')).find((el) =>
                        /Connect|连接/i.test(el.textContent || '')
                      );
                      if (!button) return { ok: false, reason: 'card_connect_missing' };
                      button.click();
                      return { ok: true };
                    })()""",
                    timeout_sec=8.0,
                )
                assert isinstance(open_dialog, dict)
                assert open_dialog.get("ok") is True, f"failed to open dialog: {open_dialog}"

                click_connect = wait_for_state(
                    client,
                    page,
                    """(() => {
                      const dialog = document.querySelector('[role="dialog"]');
                      if (!dialog) return { ready: false };
                      const button = Array.from(dialog.querySelectorAll('button')).find((el) =>
                        /Connect|连接/i.test(el.textContent || '')
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
                      const probe = logs.find((item) => item.url.includes('/api/v1/integrations/mcp/probe'));
                      const scan = logs.find((item) => item.url.includes('/api/v1/integrations/mcp/scan'));
                      const verify = logs.find((item) => item.url.includes('/api/v1/integrations/mcp/verify'));
                      const probeData = probe?.body?.data ?? null;
                      const reasonCode = probeData?.reasonCode ?? null;
                      const shouldBlock = probeData?.shouldBlockConnect ?? null;
                      const text = String(document.body?.innerText || '');
                      return {
                        ready: !!probe,
                        probeStatus: probe?.status ?? null,
                        reasonCode,
                        shouldBlock,
                        scanSeen: !!scan,
                        verifySeen: !!verify,
                        hasBlockMessage: /not running|服务未启动/i.test(text),
                        scanStatus: scan?.status ?? null,
                        verifyStatus: verify?.status ?? null,
                      };
                    })()""",
                    timeout_sec=45.0,
                )
                assert fetch_chain.get("probeStatus") == 200
                assert fetch_chain.get("reasonCode") == "connection_refused"
                assert fetch_chain.get("shouldBlock") is True
                assert fetch_chain.get("scanSeen") is False
                assert fetch_chain.get("verifySeen") is False
                assert fetch_chain.get("hasBlockMessage") is True
            break
        except RuntimeError as exc:
            last_open_error = exc
            if not _is_retryable_open_mcp_error(exc) or attempt == 2:
                raise
            time.sleep(2.0)
    else:
        raise AssertionError(f"failed to open MCP page after retries: {last_open_error}")


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_integration_catalog_tls_verification_failed_end_to_end() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    with _temporary_self_signed_tls_server() as tls_url:
        probe = http_json(
            "POST",
            f"{api_url}/api/v1/integrations/mcp/probe",
            {"url": tls_url, "timeout": 3},
        )
        assert isinstance(probe, dict)
        probe_data = probe.get("data")
        assert isinstance(probe_data, dict)
        assert probe_data.get("status") == "unreachable"
        assert probe_data.get("reasonCode") == "tls_verification_failed"
        assert probe_data.get("shouldBlockConnect") is True

        warm_ui_route("/settings/integrationCatalog")
        last_open_error: RuntimeError | None = None
        for attempt in range(3):
            try:
                with open_mcp_page(f"{ui_url}/settings/integrationCatalog", timeout_ms=90_000) as (client, page):
                    fetch_spy = client.evaluate(
                        page,
                        f"""(() => {{
                          const forcedProbeUrl = {tls_url!r};
                          if (!window.__integrationFetchLogs) {{
                            window.__integrationFetchLogs = [];
                          }}
                          if (!window.__integrationFetchWrapped) {{
                            window.__integrationFetchWrapped = true;
                            const origFetch = window.fetch.bind(window);
                            window.fetch = async (...args) => {{
                              const req = args[0];
                              const init = args[1] || {{}};
                              const url = typeof req === 'string' ? req : req?.url;
                              let nextArgs = args;
                              if (String(url || '').includes('/api/v1/integrations/mcp/probe')) {{
                                try {{
                                  const payload = JSON.parse(String(init.body || '{{}}'));
                                  payload.url = forcedProbeUrl;
                                  const nextInit = {{ ...init, body: JSON.stringify(payload) }};
                                  nextArgs = [req, nextInit];
                                }} catch (_err) {{
                                  nextArgs = args;
                                }}
                              }}
                              const resp = await origFetch(...nextArgs);
                              let body = null;
                              try {{
                                body = await resp.clone().json();
                              }} catch (_err) {{
                                body = null;
                              }}
                              window.__integrationFetchLogs.push({{
                                url: String(url || ''),
                                method: (init.method || req?.method || 'GET').toUpperCase(),
                                status: resp.status,
                                body,
                              }});
                              return resp;
                            }};
                          }}
                          return {{ ready: true }};
                        }})()""",
                        timeout_sec=8.0,
                    )
                    assert isinstance(fetch_spy, dict)
                    assert fetch_spy.get("ready") is True

                    open_dialog = client.evaluate(
                        page,
                        """(() => {
                          const titles = Array.from(document.querySelectorAll('h4'));
                          const title = titles.find((el) => /Unreal Engine|虚幻引擎/i.test(el.textContent || ''));
                          if (!title) return { ok: false, reason: 'entry_missing' };
                          const card = title.closest('div');
                          if (!card) return { ok: false, reason: 'card_missing' };
                          const button = Array.from(card.querySelectorAll('button')).find((el) =>
                            /Connect|连接/i.test(el.textContent || '')
                          );
                          if (!button) return { ok: false, reason: 'card_connect_missing' };
                          button.click();
                          return { ok: true };
                        })()""",
                        timeout_sec=8.0,
                    )
                    assert isinstance(open_dialog, dict)
                    assert open_dialog.get("ok") is True, f"failed to open dialog: {open_dialog}"

                    click_connect = wait_for_state(
                        client,
                        page,
                        """(() => {
                          const dialog = document.querySelector('[role="dialog"]');
                          if (!dialog) return { ready: false };
                          const button = Array.from(dialog.querySelectorAll('button')).find((el) =>
                            /Connect|连接/i.test(el.textContent || '')
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
                          const probe = logs.find((item) => item.url.includes('/api/v1/integrations/mcp/probe'));
                          const scan = logs.find((item) => item.url.includes('/api/v1/integrations/mcp/scan'));
                          const verify = logs.find((item) => item.url.includes('/api/v1/integrations/mcp/verify'));
                          const probeData = probe?.body?.data ?? null;
                          const reasonCode = probeData?.reasonCode ?? null;
                          const shouldBlock = probeData?.shouldBlockConnect ?? null;
                          const text = String(document.body?.innerText || '');
                          return {
                            ready: !!probe,
                            probeStatus: probe?.status ?? null,
                            reasonCode,
                            shouldBlock,
                            scanSeen: !!scan,
                            verifySeen: !!verify,
                            hasTlsMessage: /TLS[^\\n]*(certificate|证书|Zertifikat|証明書|인증서)/i.test(text),
                          };
                        })()""",
                        timeout_sec=45.0,
                    )
                    assert fetch_chain.get("probeStatus") == 200
                    assert fetch_chain.get("reasonCode") == "tls_verification_failed"
                    assert fetch_chain.get("shouldBlock") is True
                    assert fetch_chain.get("scanSeen") is False
                    assert fetch_chain.get("verifySeen") is False
                    assert fetch_chain.get("hasTlsMessage") is True
                break
            except RuntimeError as exc:
                last_open_error = exc
                if not _is_retryable_open_mcp_error(exc) or attempt == 2:
                    raise
                time.sleep(2.0)
        else:
            raise AssertionError(f"failed to open MCP page after retries: {last_open_error}")
