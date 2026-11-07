"""Real-Chromium proof that a download the agent asks for is judged at the address it came from.

``download_url`` asks the page to navigate to the URL, so it reaches whatever a navigation reaches: a hostname whose
DNS answer is cloud metadata is never dialed, a ``javascript:`` URL does not run inside the page, a redirect into
loopback is refused and nothing is saved, a redirect that lands on a page leaves the tab blank, and the page's own
download listener does not process a download a second time. A request that gives up stops the navigation it started,
so an answer still on its way when it gives up does not land afterwards. A session whose context has no request filter
has nothing but the navigator's policy between the agent and the network, so the local-mode scenarios run unfiltered;
the product's filtered contexts are covered where the filter and the policy must agree, and where a redirect hop leaves
the filter blind (it is never handed one). The hosts are fake: the process resolver answers ``public.test`` with a
public address and ``meta.test`` with the metadata address while Chromium connects both to the loopback test servers,
so a request the policy lets through lands for real and one it refuses is proven by the server never hearing of it.
Downloads a page starts itself are in ``test_download_page_started_integration``.
Run with: `pytest -m integration tests/toolkits/browser/test_download_url_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_integration import (
    DNS_ANSWERS,
    SECRET_FILE,
    SETTLE_S,
    attachment,
    kept_by_browser,
    kept_by_browser_once_settled,
    open_session,
    point_browser_tmpdir,
    saved_names,
    start_page_navigation,
    until,
)
from tests.toolkits.browser._fake_dns import process_dns, url_on
from tests.toolkits.browser._redirect_servers import page, redirect, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_NO_DOWNLOAD_TIMEOUT_S = 3.0
# How long a server holds an answer back, so the request that abandons it is gone before it would have arrived.
_SLOW_S = 3.0
_IN_TIME_S = 0.5


@pytest.fixture(autouse=True)
def _process_dns() -> Iterator[None]:
    with process_dns(DNS_ANSWERS):
        yield


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


@pytest.fixture
def browser_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return point_browser_tmpdir(tmp_path, monkeypatch)


async def _abandon_once_heard(session: BrowserSession, url: str, heard: Callable[[], bool]) -> None:
    """Start a download request and give up on it as soon as a server has the request, before it answers."""
    request = asyncio.create_task(session.download_url(url))
    await until(heard)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request


class TestRedirectOutOfThePublicInternet:
    """The request filter is never handed a redirect hop, so the final address is judged after the fact."""

    async def test_a_redirect_into_loopback_is_refused_and_nothing_is_saved(self, downloads_dir: Path) -> None:
        with (
            serve({"/secret.txt": SECRET_FILE}) as internal,
            serve({"/go": redirect(internal.url("/secret.txt"))}) as site,
        ):
            async with open_session(downloads_dir, local=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
                    await session.download_url(url_on("public.test", site, "/go"))
                await asyncio.sleep(SETTLE_S)

                assert session.list_downloads() == []
            assert saved_names(downloads_dir) == []

    async def test_a_redirect_that_lands_on_an_internal_page_leaves_the_tab_blank(self, downloads_dir: Path) -> None:
        internal_page = page("INTERNAL-PAGE-CONTENT")
        with (
            serve({"/internal": internal_page}) as internal,
            serve({"/go": redirect(internal.url("/internal"))}) as site,
        ):
            async with open_session(downloads_dir, local=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
                    await session.download_url(url_on("public.test", site, "/go"), timeout=_NO_DOWNLOAD_TIMEOUT_S)

                tab = session.get_active_page()
                assert tab.url == "about:blank"
                assert "INTERNAL-PAGE-CONTENT" not in await tab.content()

    async def test_a_public_download_is_saved_exactly_once_and_the_browser_keeps_nothing_of_it(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        with serve({"/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                result = await session.download_url(url_on("public.test", site, "/file"))
                await asyncio.sleep(SETTLE_S)

                assert result is not None
                assert Path(result.path).read_bytes() == b"hello"
                assert len(session.list_downloads()) == 1
                assert await kept_by_browser_once_settled(browser_tmp) == []  # the saved copy is the only one
            assert saved_names(downloads_dir) == ["a.txt"]


class TestLocalMode:
    """Local mode lets a URL the agent names reach its own origin and nothing else private."""

    @pytest.mark.parametrize("filtered", [True, False], ids=["filtered", "unfiltered"])
    async def test_a_named_loopback_origin_is_saved_once_and_the_listener_resumes_afterwards(
        self, downloads_dir: Path, filtered: bool
    ) -> None:
        with serve({"/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=True, filtered=filtered) as session:
                result = await session.download_url(site.url("/file"))
                await asyncio.sleep(SETTLE_S)

                assert result is not None
                assert len(session.list_downloads()) == 1
                assert saved_names(downloads_dir) == ["a.txt"]

                # a download the page starts itself is still the listener's to save
                await start_page_navigation(session, site.url("/file"))
                await until(lambda: len(session.list_downloads()) == 2)

    async def test_a_redirect_into_another_private_origin_is_refused_and_nothing_is_saved(
        self, downloads_dir: Path
    ) -> None:
        with (
            serve({"/secret.txt": SECRET_FILE}) as internal,
            serve({"/go": redirect(internal.url("/secret.txt"))}) as site,
        ):
            async with open_session(downloads_dir, local=True, filtered=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
                    await session.download_url(site.url("/go"))
                await asyncio.sleep(SETTLE_S)

                assert session.list_downloads() == []
            assert saved_names(downloads_dir) == []

    async def test_a_hostname_that_resolves_to_cloud_metadata_is_never_dialed(self, downloads_dir: Path) -> None:
        with serve({"/creds": SECRET_FILE}) as service:
            async with open_session(downloads_dir, local=True, filtered=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="metadata"):
                    await session.download_url(url_on("meta.test", service, "/creds"))
                await asyncio.sleep(SETTLE_S)

                assert session.list_downloads() == []
            assert service.hits == []

    async def test_a_javascript_url_is_refused_and_does_not_run_in_the_page(self, downloads_dir: Path) -> None:
        with serve({"/home": page("home")}) as site:
            async with open_session(downloads_dir, local=True, filtered=False) as session:
                await session.navigate(site.url("/home"))

                with pytest.raises(BrowserNavigationBlockedError, match="Unsupported navigation scheme"):
                    await session.download_url("javascript:void(fetch('/js-ran-in-page'))")
                await asyncio.sleep(SETTLE_S)
                assert "/js-ran-in-page" not in site.paths()

                # the probe is real: a fetch that does run in the page is heard by the server
                await session.get_active_page().evaluate("() => fetch('/js-control')")
                await asyncio.sleep(SETTLE_S)
                assert "/js-control" in site.paths()


class TestAbandonedRequests:
    """A request that stops waiting stops its navigation, so an answer still on its way does not land afterwards.

    Each scenario gives up as soon as a server has the request, while the answer is still on its way.
    """

    async def test_a_download_that_would_start_after_the_request_is_gone_never_arrives(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        with serve({"/slow": replace(attachment("late.txt", b"LATE"), delay_s=_SLOW_S)}) as site:
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                await _abandon_once_heard(session, url_on("public.test", site, "/slow"), lambda: bool(site.hits))
                await asyncio.sleep(_SLOW_S + SETTLE_S)

                assert session.list_downloads() == []
                assert kept_by_browser(browser_tmp) == []
            assert saved_names(downloads_dir) == []
            assert site.paths() == ["/slow"]

    async def test_a_page_that_would_arrive_after_the_request_is_gone_never_replaces_the_tab(
        self, downloads_dir: Path
    ) -> None:
        slow_internal_page = replace(page("INTERNAL-PAGE-CONTENT"), delay_s=_SLOW_S)
        with (
            serve({"/internal": slow_internal_page}) as internal,
            serve({"/go": redirect(internal.url("/internal"))}) as site,
        ):
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                await _abandon_once_heard(session, url_on("public.test", site, "/go"), lambda: bool(internal.hits))
                await asyncio.sleep(_SLOW_S + SETTLE_S)

                tab = session.get_active_page()
                assert tab.url == "about:blank"
                assert "INTERNAL-PAGE-CONTENT" not in await tab.content()
            assert internal.paths() == ["/internal"]

    async def test_a_request_that_is_answered_in_time_is_saved(self, downloads_dir: Path) -> None:
        with serve({"/slow": replace(attachment("a.txt", b"hello"), delay_s=_IN_TIME_S)}) as site:
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                result = await session.download_url(url_on("public.test", site, "/slow"))

                assert result is not None
                assert Path(result.path).read_bytes() == b"hello"
