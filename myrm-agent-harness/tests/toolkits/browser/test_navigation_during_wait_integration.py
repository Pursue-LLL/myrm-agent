"""Real-Chromium proof that a page navigating itself during the readiness wait still lands on its final document.

On a domain where networkidle has been seen to fail, SMART goes straight to the hybrid probe, which holds a
DOM-quiet window open for half a second. A page that redirects itself inside that window destroys the probe's
document; ``navigate()`` used to raise the driver's "Execution context was destroyed" error instead of
waiting for the page the script was sending the tab to. Run with:
`pytest -m integration tests/toolkits/browser/test_navigation_during_wait_integration.py`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.web_fetch.router import get_global_domain_metrics_manager
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._redirect_servers import Reply, Site, page, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_NETWORKIDLE_SAMPLES_THAT_DISABLE_THE_FAST_PATH = 20


@asynccontextmanager
async def _local_session() -> AsyncIterator[BrowserSession]:
    pool = GlobalBrowserPool(max_browsers=1)
    session = BrowserSession(pool, ContextType.AGENT, allow_private_networks=True)
    try:
        await session.new_tab()
        yield session
    finally:
        await session.close()
        await pool.shutdown()


def _redirecting_page(target: str, *, after_ms: int) -> Reply:
    script = f"setTimeout(() => {{ location = '{target}'; }}, {after_ms})"
    return Reply(
        body=f"<!DOCTYPE html><html><head></head><body>leaving<script>{script}</script></body></html>".encode()
    )


def _learn_that_networkidle_fails(site: Site) -> None:
    domain = site.base_url.removeprefix("http://")
    metrics = get_global_domain_metrics_manager().get_or_create(domain)
    for _ in range(_NETWORKIDLE_SAMPLES_THAT_DISABLE_THE_FAST_PATH):
        metrics.record_networkidle_result(success=False)


async def test_a_page_redirecting_itself_during_the_hybrid_probe_lands_on_the_final_page() -> None:
    with serve({"/start": _redirecting_page("/final", after_ms=300), "/final": page("arrived")}) as site:
        _learn_that_networkidle_fails(site)
        async with _local_session() as session:
            await session.navigate(site.url("/start"))

            tab = session.get_active_page()
            assert tab.url == site.url("/final")
            assert "arrived" in await tab.content()
        assert site.paths() == ["/start", "/final"]
