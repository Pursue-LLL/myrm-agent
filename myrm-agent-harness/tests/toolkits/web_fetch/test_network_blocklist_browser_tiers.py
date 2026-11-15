"""The browser and stealth tiers cannot see redirect hops, so they judge the requested URL and the page they ended on.

A listed requested URL is refused before a page is acquired or the browser starts; a listed page the browser ended
on is never returned. Both verdicts are terminal (``NetworkBlocklistError``), so no other tier tries the URL.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.fetchers.browser_fetcher import BrowserFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.stealth_fetcher import StealthFetcher
from myrm_agent_harness.toolkits.web_fetch.fetchers.target_guard import NetworkBlocklistError

# Scrapling builds its lxml parser with an option lxml now warns about; the project turns warnings into errors.
pytestmark = pytest.mark.filterwarnings("ignore:The 'strip_cdata' option")

_STEALTH = "myrm_agent_harness.toolkits.web_fetch.fetchers.stealth_fetcher"
_scrapling_available = importlib.util.find_spec("scrapling") is not None


@pytest.mark.asyncio
class TestBrowserTier:
    @staticmethod
    def _pool() -> MagicMock:
        tab = MagicMock()
        tab.content = AsyncMock(return_value="<html></html>")
        pool = MagicMock()
        pool.acquire_page = AsyncMock(return_value=(tab, "crawl"))
        pool.release_page = AsyncMock()
        return pool

    async def test_a_listed_requested_url_is_refused_before_a_page_is_acquired(self) -> None:
        pool = self._pool()
        fetcher = BrowserFetcher(browser_pool=pool, network_blocklist=("listed.example",))

        with pytest.raises(NetworkBlocklistError):
            await fetcher.fetch("https://listed.example/a")

        pool.acquire_page.assert_not_awaited()

    async def test_a_page_the_browser_ended_on_is_judged_and_its_content_is_not_read(self) -> None:
        pool = self._pool()
        landed = AsyncMock(return_value=("t", "https://listed.example/landing", 200))
        fetcher = BrowserFetcher(browser_pool=pool, network_blocklist=("listed.example",))

        with (
            patch("myrm_agent_harness.toolkits.browser.navigation.Navigator.goto", landed),
            pytest.raises(NetworkBlocklistError),
        ):
            await fetcher.fetch("https://start.example/a")

        pool.acquire_page.return_value[0].content.assert_not_awaited()
        pool.release_page.assert_awaited_once()

    async def test_an_unlisted_page_is_returned_as_before(self) -> None:
        pool = self._pool()
        landed = AsyncMock(return_value=("t", "https://start.example/a", 200))
        fetcher = BrowserFetcher(browser_pool=pool, network_blocklist=("listed.example",))

        with patch("myrm_agent_harness.toolkits.browser.navigation.Navigator.goto", landed):
            result = await fetcher.fetch("https://start.example/a")

        assert result is not None
        assert result.html == "<html></html>"


def _stealth_response(url: str) -> MagicMock:
    response = MagicMock()
    response.body = b"<html></html>"
    response.encoding = "utf-8"
    response.url = url
    response.status = 200
    response.headers = {}
    return response


@pytest.mark.asyncio
@pytest.mark.skipif(not _scrapling_available, reason="scrapling not installed")
class TestStealthTier:
    @pytest.fixture(autouse=True)
    def _blocklist_only(self) -> Iterator[None]:
        """The shield pins every target through a real name lookup; the blocklist needs none."""
        with patch(f"{_STEALTH}.is_ssrf_shield_enabled", return_value=False):
            yield

    async def test_a_listed_requested_url_is_refused_before_the_browser_starts(self) -> None:
        with (
            patch("scrapling.fetchers.StealthyFetcher.async_fetch", new_callable=AsyncMock) as browse,
            pytest.raises(NetworkBlocklistError),
        ):
            await StealthFetcher(network_blocklist=("listed.example",)).fetch("https://listed.example/a")

        browse.assert_not_awaited()

    async def test_the_page_the_browser_ended_on_is_judged_and_not_returned(self) -> None:
        landed = _stealth_response("https://listed.example/landing")

        with (
            patch("scrapling.fetchers.StealthyFetcher.async_fetch", new_callable=AsyncMock, return_value=landed),
            pytest.raises(NetworkBlocklistError),
        ):
            await StealthFetcher(network_blocklist=("listed.example",)).fetch("https://start.example/a")

    async def test_an_unlisted_page_is_returned_as_before(self) -> None:
        landed = _stealth_response("https://start.example/a")

        with patch("scrapling.fetchers.StealthyFetcher.async_fetch", new_callable=AsyncMock, return_value=landed):
            result = await StealthFetcher(network_blocklist=("listed.example",)).fetch("https://start.example/a")

        assert result is not None
        assert result.url == "https://start.example/a"
