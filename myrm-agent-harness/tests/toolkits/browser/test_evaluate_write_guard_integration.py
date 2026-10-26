"""Real-Chromium proof that `evaluate` does not let page JS write to a server without a person.

Outside an agent run nobody can approve, so a guarded expression is blocked (fail closed). The loopback server
records every request it receives, so "stopped" is proven by the server's hit count, not by the answer the model
sees, and a read is proven to run untouched. Run with:
`pytest -m integration tests/toolkits/browser/test_evaluate_write_guard_integration.py`.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._local_browser_session import local_session
from tests.toolkits.browser._redirect_servers import Reply, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_SETTLE_S = 0.5  # a write that slipped past the guard (a beacon is fire-and-forget) lands within this window


@pytest.mark.parametrize(
    "expression",
    [
        "fetch('/api/items/7', {method: 'DELETE'}).then(r => r.status)",
        "fetch('/api/drafts/7', {method: 'PUT', body: '{}'}).then(r => r.status)",
        "fetch('/api/orders', "
        "{headers: {'Content-Type': 'application/json'}, body: JSON.stringify({sku: 1}), method: 'POST'})"
        ".then(r => r.status)",
        "navigator.sendBeacon('/api/log', 'x')",
    ],
    ids=["delete", "put", "post-with-method-last", "send-beacon"],
)
async def test_a_page_js_write_is_stopped_before_it_reaches_the_server(expression: str) -> None:
    with serve({"/app": page("app")}) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))

            answer = await session.evaluate(expression)
            await asyncio.sleep(_SETTLE_S)

            assert answer.startswith("[BLOCKED]"), answer
            assert [hit for hit in site.hits if hit[0] != "GET"] == []


async def test_a_page_js_read_runs_untouched() -> None:
    routes = {"/app": page("app"), "/api/items": Reply(body=b'{"items": []}', content_type="application/json")}
    with serve(routes) as site:
        async with local_session() as session:
            await session.navigate(site.url("/app"))

            answer = await session.evaluate("fetch('/api/items', {method: 'GET'}).then(r => r.status)")

            assert answer == "200"
            assert site.paths("GET").count("/api/items") == 1
