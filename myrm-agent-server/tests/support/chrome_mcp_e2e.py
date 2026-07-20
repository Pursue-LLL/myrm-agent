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

from cdp_chat_support import get_e2e_api_url, get_e2e_ui_url  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402

__all__ = [
    "ChromeMcpClient",
    "McpPage",
    "ensure_desktop_viewport",
    "get_e2e_api_url",
    "get_e2e_ui_url",
    "http_json",
    "open_mcp_page",
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


def ensure_desktop_viewport(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    raw = client.evaluate(page, _ENSURE_DESKTOP_VIEWPORT_JS, timeout_sec=5.0)
    return raw if isinstance(raw, dict) else {"value": raw}


def http_json(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
) -> object:
    allowed = (get_e2e_ui_url(), get_e2e_api_url())
    if not url.startswith(allowed):
        raise ValueError(f"Chrome E2E HTTP helper only permits loopback app URLs: {url}")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310 - validated loopback
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - loopback only
            raw = response.read()
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    if status not in expected_statuses:
        raise RuntimeError(f"HTTP {method} {url} returned {status}: {raw[:500]!r}")
    return json.loads(raw) if raw else {}


def warm_ui_route(path: str, *, timeout_sec: float = 120.0) -> None:
    """HTTP GET a UI route so webpack/turbopack compiles before Chrome navigation."""
    if not path.startswith("/"):
        raise ValueError(f"warm_ui_route expects an absolute path, got: {path!r}")
    url = f"{get_e2e_ui_url()}{path}"
    request = urllib.request.Request(url, method="GET")  # noqa: S310 - loopback only
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:  # noqa: S310
        if response.status != 200:
            raise RuntimeError(f"warm_ui_route GET {url} returned HTTP {response.status}")


@contextmanager
def open_mcp_page(
    url: str,
    *,
    timeout_ms: int | None = None,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    with ChromeMcpClient() as client:
        page = client.new_page(url, timeout_ms=timeout_ms)
        ensure_desktop_viewport(client, page)
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
