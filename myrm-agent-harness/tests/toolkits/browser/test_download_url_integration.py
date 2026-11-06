"""Real-Chromium proof that a download by URL is judged like a navigation to the same URL.

``download_url`` asks the page to navigate to the URL, so it reaches whatever a navigation reaches. Each scenario below
pins one way that request used to escape the navigation policy: a hostname whose DNS answer is cloud metadata was
dialed, a ``javascript:`` URL ran inside the page, a redirect into loopback was saved to disk, a redirect that landed
on a page left the tab showing it, and the page's own download listener processed a download a second time. A session
whose context has no request filter has nothing but the navigator's policy between the agent and the network, so the
local-mode scenarios run unfiltered; the product's filtered contexts are covered where the filter and the policy must
agree. The hosts are fake: the process resolver answers ``public.test`` with a public address and ``meta.test`` with
the metadata address while Chromium connects both to the loopback test servers, so a request the policy lets through
lands for real and one it refuses is proven by the server never hearing of it. Run with:
`pytest -m integration tests/toolkits/browser/test_download_url_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.session.download_manager import DownloadConfig
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._fake_dns import launch_options_dialing_loopback, process_dns, url_on
from tests.toolkits.browser._redirect_servers import Reply, page, redirect, serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]

_DNS_ANSWERS = {"public.test": "93.184.216.34", "meta.test": "169.254.169.254"}
_DOWNLOAD_TIMEOUT_S = 10.0
_NO_DOWNLOAD_TIMEOUT_S = 3.0
_SETTLE_S = 0.5


def _attachment(name: str, body: bytes) -> Reply:
    return Reply(
        body=body,
        content_type="text/plain",
        headers=(("Content-Disposition", f'attachment; filename="{name}"'),),
    )


_SECRET_FILE = _attachment("secret.txt", b"INTERNAL-SECRET")


@pytest.fixture(autouse=True)
def _process_dns() -> Iterator[None]:
    with process_dns(_DNS_ANSWERS):
        yield


@pytest.fixture
def downloads_dir(tmp_path: Path) -> Path:
    return tmp_path / "downloads"


@asynccontextmanager
async def _session(downloads_dir: Path, *, local: bool, filtered: bool = True) -> AsyncIterator[BrowserSession]:
    """A session with download support; ``filtered=False`` leaves its context without a request filter."""
    pool = GlobalBrowserPool(
        max_browsers=1,
        config=None if filtered else BrowserPoolConfig.minimal(),
        launch_options=launch_options_dialing_loopback(_DNS_ANSWERS),
    )
    session = BrowserSession(
        pool,
        ContextType.AGENT,
        allow_private_networks=local,
        download_config=DownloadConfig(downloads_dir=downloads_dir, download_timeout_s=_DOWNLOAD_TIMEOUT_S),
    )
    try:
        await session.new_tab()
        yield session
    finally:
        await session.close()
        await pool.shutdown()


def _saved_names(downloads_dir: Path) -> list[str]:
    return sorted(path.name for path in downloads_dir.iterdir())


class TestRedirectOutOfThePublicInternet:
    """The request filter is never handed a redirect hop, so the final address is judged after the fact."""

    async def test_a_redirect_into_loopback_is_refused_and_nothing_is_saved(self, downloads_dir: Path) -> None:
        with (
            serve({"/secret.txt": _SECRET_FILE}) as internal,
            serve({"/go": redirect(internal.url("/secret.txt"))}) as site,
        ):
            async with _session(downloads_dir, local=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
                    await session.download_url(url_on("public.test", site, "/go"))
                await asyncio.sleep(_SETTLE_S)

                assert session.list_downloads() == []
            assert _saved_names(downloads_dir) == []

    async def test_a_redirect_that_lands_on_an_internal_page_leaves_the_tab_blank(self, downloads_dir: Path) -> None:
        internal_page = page("INTERNAL-PAGE-CONTENT")
        with (
            serve({"/internal": internal_page}) as internal,
            serve({"/go": redirect(internal.url("/internal"))}) as site,
        ):
            async with _session(downloads_dir, local=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
                    await session.download_url(url_on("public.test", site, "/go"), timeout=_NO_DOWNLOAD_TIMEOUT_S)

                tab = session.get_active_page()
                assert tab.url == "about:blank"
                assert "INTERNAL-PAGE-CONTENT" not in await tab.content()

    async def test_a_public_download_is_saved_exactly_once(self, downloads_dir: Path) -> None:
        with serve({"/file": _attachment("a.txt", b"hello")}) as site:
            async with _session(downloads_dir, local=False) as session:
                result = await session.download_url(url_on("public.test", site, "/file"))
                await asyncio.sleep(_SETTLE_S)

                assert result is not None
                assert Path(result.path).read_bytes() == b"hello"
                assert len(session.list_downloads()) == 1
            assert _saved_names(downloads_dir) == ["a.txt"]


class TestLocalMode:
    """Local mode lets a URL the agent names reach its own origin and nothing else private."""

    @pytest.mark.parametrize("filtered", [True, False], ids=["filtered", "unfiltered"])
    async def test_a_named_loopback_origin_is_saved_once_and_the_listener_resumes_afterwards(
        self, downloads_dir: Path, filtered: bool
    ) -> None:
        with serve({"/file": _attachment("a.txt", b"hello")}) as site:
            async with _session(downloads_dir, local=True, filtered=filtered) as session:
                result = await session.download_url(site.url("/file"))
                await asyncio.sleep(_SETTLE_S)

                assert result is not None
                assert len(session.list_downloads()) == 1
                assert _saved_names(downloads_dir) == ["a.txt"]

                # a download the page starts itself is still the listener's to save
                await session.get_active_page().evaluate("(url) => { window.location.href = url; }", site.url("/file"))
                async with asyncio.timeout(_DOWNLOAD_TIMEOUT_S):
                    while len(session.list_downloads()) < 2:
                        await asyncio.sleep(0.05)

    async def test_a_redirect_into_another_private_origin_is_refused_and_nothing_is_saved(
        self, downloads_dir: Path
    ) -> None:
        with (
            serve({"/secret.txt": _SECRET_FILE}) as internal,
            serve({"/go": redirect(internal.url("/secret.txt"))}) as site,
        ):
            async with _session(downloads_dir, local=True, filtered=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="SSRF blocked"):
                    await session.download_url(site.url("/go"))
                await asyncio.sleep(_SETTLE_S)

                assert session.list_downloads() == []
            assert _saved_names(downloads_dir) == []

    async def test_a_hostname_that_resolves_to_cloud_metadata_is_never_dialed(self, downloads_dir: Path) -> None:
        with serve({"/creds": _SECRET_FILE}) as service:
            async with _session(downloads_dir, local=True, filtered=False) as session:
                with pytest.raises(BrowserNavigationBlockedError, match="metadata"):
                    await session.download_url(url_on("meta.test", service, "/creds"))
                await asyncio.sleep(_SETTLE_S)

                assert session.list_downloads() == []
            assert service.hits == []

    async def test_a_javascript_url_is_refused_and_does_not_run_in_the_page(self, downloads_dir: Path) -> None:
        with serve({"/home": page("home")}) as site:
            async with _session(downloads_dir, local=True, filtered=False) as session:
                await session.navigate(site.url("/home"))

                with pytest.raises(BrowserNavigationBlockedError, match="Unsupported navigation scheme"):
                    await session.download_url("javascript:void(fetch('/js-ran-in-page'))")
                await asyncio.sleep(_SETTLE_S)
                assert "/js-ran-in-page" not in site.paths()

                # the probe is real: a fetch that does run in the page is heard by the server
                await session.get_active_page().evaluate("() => fetch('/js-control')")
                await asyncio.sleep(_SETTLE_S)
                assert "/js-control" in site.paths()
