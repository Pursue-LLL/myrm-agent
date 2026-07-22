"""Shared real-Chrome MCP helpers for formal UI E2E tests."""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from cdp_chat_support import (
    DISMISS_MODALS_JS,
    _e2e_api_urlopen,
    e2e_runtime_binding,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402

__all__ = [
    "ChromeMcpClient",
    "McpPage",
    "dismiss_blocking_modals",
    "ensure_desktop_viewport",
    "get_e2e_api_url",
    "get_e2e_ui_url",
    "http_json",
    "open_mcp_page",
    "prepare_e2e_ui_session",
    "wait_for_state",
    "warm_ui_route",
]

_ENSURE_DESKTOP_VIEWPORT_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore — some profiles block resizeTo
  }
  return { width: window.innerWidth, height: window.innerHeight };
})()"""


def ensure_desktop_viewport(
    client: ChromeMcpClient, page: McpPage
) -> dict[str, object]:
    raw = client.evaluate(page, _ENSURE_DESKTOP_VIEWPORT_JS, timeout_sec=5.0)
    return raw if isinstance(raw, dict) else {"value": raw}


def dismiss_blocking_modals(client: ChromeMcpClient, page: McpPage) -> None:
    """Dismiss onboarding/migration overlays that block E2E clicks (SSOT: cdp_chat_support)."""
    dismissed = client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
    assert isinstance(dismissed, dict) and dismissed.get("ok") is True, dismissed
    boot = client.evaluate(
        page,
        """(() => {
          try { localStorage.setItem('myrm_boot_shown', '1'); } catch (err) {
            return { ok: false, err: String(err) };
          }
          return { ok: true };
        })()""",
        timeout_sec=5.0,
    )
    assert isinstance(boot, dict) and boot.get("ok") is True, boot


def prepare_e2e_ui_session(api_url: str) -> None:
    """Mark onboarding complete so PageLayout does not overlay the chat during E2E."""
    http_json(
        "POST",
        f"{api_url}/api/v1/config/onboarding/complete",
        expected_statuses=frozenset({200, 201}),
    )


def http_json(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
) -> object:
    allowed = (get_e2e_ui_url(), get_e2e_api_url())
    if not url.startswith(allowed):
        raise ValueError(
            f"Chrome E2E HTTP helper only permits loopback app URLs: {url}"
        )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - validated loopback
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        response = _e2e_api_urlopen(
            request, timeout_sec=30.0
        )  # noqa: S310 - loopback only
        with response as http_response:
            raw = http_response.read()
            status = http_response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    if status not in expected_statuses:
        raise RuntimeError(f"HTTP {method} {url} returned {status}: {raw[:500]!r}")
    return json.loads(raw) if raw else {}


def warm_ui_route(path: str, *, timeout_sec: float | None = None) -> None:
    """HTTP GET a UI route so webpack/turbopack compiles before Chrome navigation."""
    import os

    if not path.startswith("/"):
        raise ValueError(f"warm_ui_route expects an absolute path, got: {path!r}")
    url = f"{get_e2e_ui_url()}{path}"
    wait_sec = (
        timeout_sec
        if timeout_sec is not None
        else float(os.environ.get("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "180"))
    )
    poll_sec = float(os.environ.get("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "2"))
    deadline = time.monotonic() + wait_sec
    last_error: BaseException | None = None
    while time.monotonic() < deadline:
        request = urllib.request.Request(url, method="GET")  # noqa: S310 - loopback only
        per_attempt = max(5.0, min(30.0, deadline - time.monotonic()))
        try:
            with urllib.request.urlopen(request, timeout=per_attempt) as response:  # noqa: S310
                if response.status == 200:
                    return
                last_error = RuntimeError(
                    f"warm_ui_route GET {url} returned HTTP {response.status}"
                )
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
        time.sleep(poll_sec)
    raise RuntimeError(
        f"warm_ui_route GET {url} failed after {wait_sec:.0f}s: {last_error!r}"
    )


def _wait_for_shpoib_runtime_ready(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 60.0,
) -> None:
    """Wait until mux-injected private Backend binding is healthy after reload."""
    wait_for_state(
        client,
        page,
        """(async () => {
          if (typeof window.__MYRM_E2E_RUNTIME_READY__ === 'undefined') {
            return { ready: false, phase: 'missing' };
          }
          try {
            await window.__MYRM_E2E_RUNTIME_READY__;
            return { ready: true };
          } catch (error) {
            return { ready: false, phase: 'error', error: String(error) };
          }
        })()""",
        timeout_sec=timeout_sec,
    )


def _reapply_shpoib_runtime_after_reload(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 120.0,
) -> None:
    """Reload clears window globals; re-run bootstrap fetch against private :180xx API."""
    import os

    api_base = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_base, timeout_sec=timeout_sec):
        raise RuntimeError(f"SHPOIB private API not ready before rebind: {api_base}")
    bootstrap_js = e2e_runtime_bootstrap_apply_js()
    if bootstrap_js is None:
        raise RuntimeError("SHPOIB bootstrap JS missing after reload")
    observed = client.evaluate(page, bootstrap_js, timeout_sec=timeout_sec)
    if not isinstance(observed, dict) or observed.get("ok") is not True:
        raise RuntimeError(f"SHPOIB runtime rebind after reload failed: {observed}")
    rebind_timeout = float(os.environ.get("MYRM_SHPOIB_REBIND_TIMEOUT_SEC", str(timeout_sec)))
    _wait_for_shpoib_runtime_ready(client, page, timeout_sec=rebind_timeout)


@contextmanager
def open_mcp_page(
    url: str,
    *,
    timeout_ms: int | None = None,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    with ChromeMcpClient() as client:
        page = client.new_page(url, timeout_ms=timeout_ms)
        ensure_desktop_viewport(client, page)
        if e2e_runtime_binding() is not None:
            resolved_timeout_ms = timeout_ms if timeout_ms is not None else 60_000
            client.reload(page, timeout_ms=resolved_timeout_ms)
            _reapply_shpoib_runtime_after_reload(client, page)
        wait_for_state(
            client,
            page,
            """(() => ({
              ready: !!document.querySelector('[data-testid="app-layout"]'),
            }))()""",
            timeout_sec=90.0,
        )
        yield client, page


def _coerce_evaluate_result(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"value": raw}


def wait_for_state(
    client: ChromeMcpClient,
    page: McpPage,
    expression: str,
    *,
    timeout_sec: float = 45.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        raw = client.evaluate(
            page,
            expression,
            timeout_sec=max(5.0, min(30.0, remaining)),
        )
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return last
        time.sleep(0.25)
    raise AssertionError(f"Browser state did not become ready: {last}")
