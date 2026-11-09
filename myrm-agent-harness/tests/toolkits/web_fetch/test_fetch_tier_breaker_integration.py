"""FetchEngine drives a real tier breaker: only contrasted failures move a domain's start tier.

The fetchers are stubs, so every scenario counts exactly which tiers a crawl touched.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.protocols import FetcherType
from myrm_agent_harness.toolkits.web_fetch.router import DomainMetricsManager, TierBreaker
from tests.toolkits.web_fetch._degradation_support import RICH_HTML, http_result, make_document, stub_fetchers

URL = "http://example.com/page"


@dataclass(slots=True)
class _Site:
    engine: FetchEngine
    http: AsyncMock
    browser: AsyncMock
    stealth: AsyncMock

    async def visit(self, url: str = URL) -> bool:
        doc, _result = await self.engine._crawl_with_degradation(url, allow_escalation=False)
        return doc is not None


@pytest.fixture
async def site(tmp_path: Path) -> AsyncIterator[_Site]:
    engine = FetchEngine()
    http, browser, stealth = stub_fetchers(engine)
    engine._tier_breaker = TierBreaker()
    engine._domain_metrics = DomainMetricsManager(storage_path=tmp_path / "domain_metrics.json")
    engine._pipeline.aprocess.return_value = make_document()
    yield _Site(engine, http, browser, stealth)
    await engine.shutdown()


def _http_blocked_browser_works(site: _Site) -> None:
    site.http.fetch.return_value = None
    site.browser.fetch.return_value = http_result(RICH_HTML)


async def test_a_tier_the_browser_keeps_making_up_for_is_no_longer_tried_first(site: _Site) -> None:
    _http_blocked_browser_works(site)

    for _ in range(3):
        assert await site.visit()
    assert (site.http.fetch.await_count, site.browser.fetch.await_count) == (3, 3)

    assert await site.visit()

    assert (site.http.fetch.await_count, site.browser.fetch.await_count) == (3, 4)


async def test_the_breaker_keys_a_domain_by_host_not_by_page(site: _Site) -> None:
    _http_blocked_browser_works(site)

    for path in ("/a", "/b", "/c"):
        await site.visit(f"http://EXAMPLE.com{path}")
    await site.visit("http://example.com/d")

    assert site.http.fetch.await_count == 3


async def test_failures_no_tier_made_up_for_never_move_the_start_tier(site: _Site) -> None:
    site.http.fetch.return_value = None
    site.browser.fetch.return_value = None
    site.stealth.fetch.return_value = None

    for _ in range(10):
        assert not await site.visit()

    assert site.http.fetch.await_count == 10


async def test_an_open_tier_is_probed_and_one_success_closes_it(site: _Site) -> None:
    _http_blocked_browser_works(site)
    for _ in range(3):
        await site.visit()
    for _ in range(9):
        await site.visit()
    assert site.http.fetch.await_count == 3  # nine visits went straight to the browser

    site.http.fetch.return_value = http_result(RICH_HTML)
    await site.visit()  # the tenth visit probes HTTP, which works again
    await site.visit()

    assert site.http.fetch.await_count == 5


async def test_a_successful_crawl_leaves_no_failure_history(site: _Site) -> None:
    site.http.fetch.return_value = http_result(RICH_HTML)

    assert await site.visit()

    assert site.engine._domain_metrics.get("example.com") is None


async def test_failed_attempts_feed_the_failure_history_the_stale_site_hint_reads(site: _Site) -> None:
    _http_blocked_browser_works(site)

    for _ in range(3):
        await site.visit()

    metrics = site.engine._domain_metrics.get("example.com")
    assert metrics is not None
    assert metrics.get_recent_failures_count(FetcherType.HTTP) == 3
    assert metrics.get_recent_failures_count(FetcherType.BROWSER) == 0


async def test_shutdown_saves_failure_history_the_save_schedule_has_not_reached(site: _Site, tmp_path: Path) -> None:
    _http_blocked_browser_works(site)
    await site.visit()
    saved = tmp_path / "domain_metrics.json"
    assert not saved.exists()

    await site.engine.shutdown()

    assert "example.com" in json.loads(saved.read_text())
