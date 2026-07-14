"""Three real Chrome MCP mux contexts keep exact page ownership in parallel."""

from __future__ import annotations

import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TypedDict

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402

BASE_URL = "http://127.0.0.1:3000/"
STATE_URL = f"{BASE_URL}theme-init.js"


class PageProbe(TypedDict):
    page_id: int
    target_id: str
    href: str
    body_length: int
    has_layout: bool
    has_input: bool


class BrowserGlobals(TypedDict):
    localStorage: str | None
    cookie: bool
    databases: list[str]
    serviceWorkers: list[str]


def _read_browser_globals(
    client: ChromeMcpClient,
    page: McpPage,
    marker: str,
) -> BrowserGlobals:
    raw = client.evaluate(
        page,
        f"""(async () => ({{
          localStorage: localStorage.getItem('pytest-context'),
          cookie: document.cookie.includes('pytest_context={marker}'),
          databases: (await indexedDB.databases()).map((item) => item.name),
          serviceWorkers: (await navigator.serviceWorker.getRegistrations())
            .map((item) => new URL(item.scope).pathname),
        }}))()""",
        timeout_sec=5.0,
    )
    if not isinstance(raw, dict):
        raise AssertionError(f"Expected browser global state object, got {raw!r}")
    databases = raw.get("databases")
    service_workers = raw.get("serviceWorkers")
    if not isinstance(databases, list) or not all(isinstance(item, str) for item in databases):
        raise AssertionError(f"Expected IndexedDB name list, got {databases!r}")
    if not isinstance(service_workers, list) or not all(isinstance(item, str) for item in service_workers):
        raise AssertionError(f"Expected Service Worker scope list, got {service_workers!r}")
    local_storage = raw.get("localStorage")
    cookie = raw.get("cookie")
    if local_storage is not None and not isinstance(local_storage, str):
        raise AssertionError(f"Expected localStorage string, got {local_storage!r}")
    if not isinstance(cookie, bool):
        raise AssertionError(f"Expected cookie boolean, got {cookie!r}")
    return {
        "localStorage": local_storage,
        "cookie": cookie,
        "databases": databases,
        "serviceWorkers": service_workers,
    }


def _open_probe_and_hold(barrier: threading.Barrier) -> PageProbe:
    with ChromeMcpClient() as client:
        page = client.new_page(BASE_URL, timeout_ms=15_000)
        deadline = time.monotonic() + 15.0
        raw: object = None
        while time.monotonic() < deadline:
            raw = client.evaluate(
                page,
                """({
                  href: location.href,
                  bodyLength: document.body?.innerText?.length ?? 0,
                  hasLayout: !!document.querySelector('[data-testid="app-layout"]'),
                  hasInput: !!document.querySelector('[data-chat-input]'),
                })""",
                timeout_sec=5.0,
            )
            if isinstance(raw, dict) and raw.get("hasLayout") is True and raw.get("hasInput") is True:
                break
            time.sleep(0.25)
        if not isinstance(raw, dict):
            raise AssertionError(f"Expected DOM probe object, got {raw!r}")
        barrier.wait(timeout=30.0)
        return {
            "page_id": page.page_id,
            "target_id": page.target_id,
            "href": str(raw.get("href") or ""),
            "body_length": int(raw.get("bodyLength") or 0),
            "has_layout": raw.get("hasLayout") is True,
            "has_input": raw.get("hasInput") is True,
        }


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_three_mux_clients_own_interactive_tabs_concurrently() -> None:
    barrier = threading.Barrier(3)
    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="chrome-mcp-e2e") as pool:
        results = list(pool.map(_open_probe_and_hold, [barrier] * 3))

    assert len({item["page_id"] for item in results}) == 3
    assert len({item["target_id"] for item in results}) == 3
    for item in results:
        assert item["href"] == BASE_URL
        assert item["body_length"] > 0
        assert item["has_layout"] is True
        assert item["has_input"] is True


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(120)
def test_isolated_browser_contexts_do_not_share_global_state() -> None:
    marker = uuid.uuid4().hex
    context_a = f"pytest-isolated-a-{marker}"
    context_b = f"pytest-isolated-b-{marker}"
    database = f"pytest-context-{marker}"
    service_worker_scope = f"/pytest-context-{marker}/"

    with ChromeMcpClient() as client_a:
        page_a = client_a.new_page(
            "about:blank",
            timeout_ms=15_000,
            isolated_context=context_a,
        )
        client_a.navigate(page_a, STATE_URL, timeout_ms=15_000)
        seeded = client_a.evaluate(
            page_a,
            f"""(() => {{
              localStorage.setItem('pytest-context', {marker!r});
              document.cookie = 'pytest_context={marker}; Path=/; SameSite=Lax';
              return {{
                localStorage: localStorage.getItem('pytest-context'),
                cookie: document.cookie.includes('pytest_context={marker}'),
              }};
            }})()""",
            timeout_sec=15.0,
        )
        client_a.evaluate(
            page_a,
            f"""(() => {{
              const request = indexedDB.open({database!r}, 1);
              request.onupgradeneeded = () => request.result.createObjectStore('state');
              request.onsuccess = () => request.result.close();
              void navigator.serviceWorker.register('/theme-init.js', {{
                scope: {service_worker_scope!r},
              }}).catch(() => undefined);
              return true;
            }})()""",
            timeout_sec=15.0,
        )
        with ChromeMcpClient() as client_b:
            page_b = client_b.new_page(
                "about:blank",
                timeout_ms=15_000,
                isolated_context=context_b,
            )
            client_b.navigate(page_b, STATE_URL, timeout_ms=15_000)
            deadline = time.monotonic() + 20.0
            seeded_globals: BrowserGlobals = {
                "localStorage": None,
                "cookie": False,
                "databases": [],
                "serviceWorkers": [],
            }
            while time.monotonic() < deadline:
                seeded_globals = _read_browser_globals(client_a, page_a, marker)
                if database in seeded_globals["databases"] and service_worker_scope in seeded_globals["serviceWorkers"]:
                    break
                time.sleep(0.25)
            isolated = _read_browser_globals(client_b, page_b, marker)

    assert isinstance(seeded, dict)
    assert seeded["localStorage"] == marker
    assert seeded["cookie"] is True
    assert database in seeded_globals["databases"]
    assert service_worker_scope in seeded_globals["serviceWorkers"]
    assert isolated["localStorage"] is None
    assert isolated["cookie"] is False
    assert database not in isolated["databases"]
    assert service_worker_scope not in isolated["serviceWorkers"]
