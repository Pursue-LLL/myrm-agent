"""Real-Chromium proof that a download is judged at the address it came from, whoever started it.

``download_url`` asks the page to navigate to the URL, so it reaches whatever a navigation reaches: a hostname whose
DNS answer is cloud metadata is never dialed, a ``javascript:`` URL does not run inside the page, a redirect into
loopback is refused and nothing is saved, a redirect that lands on a page leaves the tab blank, and the page's own
download listener does not process a download a second time. A download the page starts itself (a script, a link) is
judged like one the agent asked for, and a refused one is cancelled and deleted, also while its body is still arriving.
A request that gives up stops the navigation it started, so an answer still on its way when it gives up does not land
afterwards. A session whose context has no request filter has nothing but the navigator's policy between the agent and
the network, so the local-mode scenarios and the direct page-started request run unfiltered; the product's filtered
contexts are covered where the filter and the policy must agree, and where a redirect hop leaves the filter blind (it
is never handed one). The hosts are fake: the process resolver answers ``public.test`` with a public address and
``meta.test`` with the metadata address while Chromium connects both to the loopback test servers, so a request the
policy lets through lands for real and one it refuses is proven by the server never hearing of it. What the browser
still holds of a refused download is read from the temp dir its driver keeps downloads in, which each test points at
its own directory. Run with: `pytest -m integration tests/toolkits/browser/test_download_url_integration.py`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager, suppress
from dataclasses import replace
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession, enhancers
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
# How long a server holds an answer back, so the request that abandons it is gone before it would have arrived.
_SLOW_S = 3.0
_IN_TIME_S = 0.5
# How long the verdict on a download is held back, so a small body is fully written before the verdict arrives.
_LATE_VERDICT_S = 1.0
# A body that stalls: the server sends enough for the browser to start the download (a few bytes of plain text are
# held back for content sniffing), promises far more, and holds the connection open longer than any wait in these
# tests, so the download is still in progress whenever it is looked at.
_STALLED_BODY = b"INTERNAL-SECRET" * 512
_STALLED_BODY_LENGTH = 1_000_000
_STALL_S = 2 * _DOWNLOAD_TIMEOUT_S

_START_NAVIGATION_JS = "(url) => { window.location.href = url; }"
_CLICK_BLOB_DOWNLOAD_JS = """() => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob(['made-in-page'], { type: 'text/plain' }));
    link.download = 'made.txt';
    document.body.appendChild(link);
    link.click();
}"""


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


@pytest.fixture
def browser_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temp dir the browser driver keeps downloads in; it is read when the browser starts, so it is set first."""
    directory = tmp_path / "browser-tmp"
    directory.mkdir()
    monkeypatch.setenv("TMPDIR", str(directory))
    return directory


def _saved_names(downloads_dir: Path) -> list[str]:
    return sorted(path.name for path in downloads_dir.iterdir())


def _kept_by_browser(browser_tmp: Path) -> list[str]:
    """What the browser still holds of its downloads: a refused or abandoned one leaves nothing here."""
    return sorted(path.name for path in browser_tmp.glob("*artifacts*/*"))


async def _kept_by_browser_once_settled(browser_tmp: Path) -> list[str]:
    """``_kept_by_browser`` after the browser has finished discarding; that can lag behind the refusal."""
    with suppress(TimeoutError):
        await _until(lambda: not _kept_by_browser(browser_tmp))
    return _kept_by_browser(browser_tmp)


async def _start_page_navigation(session: BrowserSession, url: str) -> None:
    """Navigate the page the way a script or a link does, not through ``download_url``."""
    await session.get_active_page().evaluate(_START_NAVIGATION_JS, url)


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(_DOWNLOAD_TIMEOUT_S):
        while not condition():
            await asyncio.sleep(0.05)


async def _until_judged(session: BrowserSession, caplog: pytest.LogCaptureFixture) -> None:
    """Wait for the verdict on a download the page started: refused (the manager logs it) or saved."""
    await _until(lambda: "Refused a download" in caplog.text or bool(session.list_downloads()))


def _delay_verdicts(monkeypatch: pytest.MonkeyPatch, seconds: float) -> None:
    """Hold back the verdict on where a download came from; what the verdict says is unchanged."""
    judge = BrowserSession._assert_download_final_url_allowed

    async def verdict_after_a_while(session: BrowserSession, url: str) -> None:
        await asyncio.sleep(seconds)
        await judge(session, url)

    monkeypatch.setattr(BrowserSession, "_assert_download_final_url_allowed", verdict_after_a_while)


async def _abandon_once_heard(session: BrowserSession, url: str, heard: Callable[[], bool]) -> None:
    """Start a download request and give up on it as soon as a server has the request, before it answers."""
    request = asyncio.create_task(session.download_url(url))
    await _until(heard)
    request.cancel()
    with pytest.raises(asyncio.CancelledError):
        await request


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
                await _start_page_navigation(session, site.url("/file"))
                await _until(lambda: len(session.list_downloads()) == 2)

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


class TestDownloadsThePageStartsItself:
    """A download from a script or a link reaches the page's listener, which judges it like a request."""

    async def test_a_download_from_a_metadata_hostname_is_discarded_and_nothing_is_kept(
        self, downloads_dir: Path, browser_tmp: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with serve({"/home": page("home")}) as site, serve({"/creds": _SECRET_FILE}) as service:
            async with _session(downloads_dir, local=False, filtered=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await _start_page_navigation(session, url_on("meta.test", service, "/creds"))
                await _until_judged(session, caplog)

                assert session.list_downloads() == []
                assert await _kept_by_browser_once_settled(browser_tmp) == []
            assert _saved_names(downloads_dir) == []
            assert service.hits == [("GET", "/creds")]  # only keeping the body is refused; the request was made

    @pytest.mark.parametrize(
        ("filtered", "verdict_delay_s"),
        [(True, 0.0), (False, 0.0), (True, _LATE_VERDICT_S)],
        ids=["filtered", "unfiltered", "verdict-after-the-body"],
    )
    async def test_a_redirect_into_loopback_is_discarded_and_nothing_is_kept(
        self,
        downloads_dir: Path,
        browser_tmp: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
        filtered: bool,
        verdict_delay_s: float,
    ) -> None:
        # A verdict that comes after the body is complete finds nothing to cancel: the refusal has to delete it.
        if verdict_delay_s:
            _delay_verdicts(monkeypatch, verdict_delay_s)
        with (
            serve({"/secret.txt": _SECRET_FILE}) as internal,
            serve({"/home": page("home"), "/go": redirect(internal.url("/secret.txt"))}) as site,
        ):
            async with _session(downloads_dir, local=False, filtered=filtered) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await _start_page_navigation(session, url_on("public.test", site, "/go"))
                await _until_judged(session, caplog)

                assert session.list_downloads() == []
                assert await _kept_by_browser_once_settled(browser_tmp) == []
            assert _saved_names(downloads_dir) == []
            assert internal.paths() == ["/secret.txt"]

    async def test_a_refused_download_whose_body_is_still_arriving_is_stopped_and_nothing_is_kept(
        self,
        downloads_dir: Path,
        browser_tmp: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # The document route hands the browser a page's response only once it has fetched all of it, so no body stalls
        # in front of the browser while the route is in place. Deleting waits for a download to finish: only
        # cancelling gets rid of a body that never does.
        monkeypatch.setattr(enhancers, "get_dom_enhancer_script", lambda: "")
        _delay_verdicts(monkeypatch, _LATE_VERDICT_S)
        stalled_secret = replace(
            _attachment("secret.txt", _STALLED_BODY), declared_length=_STALLED_BODY_LENGTH, hold_open_s=_STALL_S
        )
        with serve({"/home": page("home")}) as site, serve({"/creds": stalled_secret}) as service:
            async with _session(downloads_dir, local=False, filtered=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await _start_page_navigation(session, url_on("meta.test", service, "/creds"))
                await _until(lambda: bool(_kept_by_browser(browser_tmp)))  # the probe sees the body arriving
                await _until_judged(session, caplog)

                assert session.list_downloads() == []
                assert await _kept_by_browser_once_settled(browser_tmp) == []
            assert _saved_names(downloads_dir) == []

    @pytest.mark.parametrize("filtered", [True, False], ids=["filtered", "unfiltered"])
    async def test_a_public_download_is_saved_once_and_the_browser_is_seen_keeping_it(
        self, downloads_dir: Path, browser_tmp: Path, filtered: bool
    ) -> None:
        with serve({"/home": page("home"), "/file": _attachment("a.txt", b"hello")}) as site:
            async with _session(downloads_dir, local=False, filtered=filtered) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await _start_page_navigation(session, url_on("public.test", site, "/file"))
                await _until(lambda: bool(session.list_downloads()))
                await asyncio.sleep(_SETTLE_S)

                assert [Path(saved.path).read_bytes() for saved in session.list_downloads()] == [b"hello"]
                # the probe is real: it lists the artifact the browser keeps of a download that was saved
                assert len(_kept_by_browser(browser_tmp)) == 1
            assert _saved_names(downloads_dir) == ["a.txt"]

    async def test_a_download_the_page_builds_itself_names_no_address_and_is_saved(self, downloads_dir: Path) -> None:
        with serve({"/home": page("home")}) as site:
            async with _session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await session.get_active_page().evaluate(_CLICK_BLOB_DOWNLOAD_JS)
                await _until(lambda: bool(session.list_downloads()))

                assert [Path(saved.path).read_bytes() for saved in session.list_downloads()] == [b"made-in-page"]


class TestAbandonedRequests:
    """A request that stops waiting stops its navigation, so an answer still on its way does not land afterwards.

    Each scenario gives up as soon as a server has the request, while the answer is still on its way.
    """

    async def test_a_download_that_would_start_after_the_request_is_gone_never_arrives(
        self, downloads_dir: Path, browser_tmp: Path
    ) -> None:
        with serve({"/slow": replace(_attachment("late.txt", b"LATE"), delay_s=_SLOW_S)}) as site:
            async with _session(downloads_dir, local=False, filtered=False) as session:
                await _abandon_once_heard(session, url_on("public.test", site, "/slow"), lambda: bool(site.hits))
                await asyncio.sleep(_SLOW_S + _SETTLE_S)

                assert session.list_downloads() == []
                assert _kept_by_browser(browser_tmp) == []
            assert _saved_names(downloads_dir) == []
            assert site.paths() == ["/slow"]

    async def test_a_page_that_would_arrive_after_the_request_is_gone_never_replaces_the_tab(
        self, downloads_dir: Path
    ) -> None:
        slow_internal_page = replace(page("INTERNAL-PAGE-CONTENT"), delay_s=_SLOW_S)
        with (
            serve({"/internal": slow_internal_page}) as internal,
            serve({"/go": redirect(internal.url("/internal"))}) as site,
        ):
            async with _session(downloads_dir, local=False, filtered=False) as session:
                await _abandon_once_heard(session, url_on("public.test", site, "/go"), lambda: bool(internal.hits))
                await asyncio.sleep(_SLOW_S + _SETTLE_S)

                tab = session.get_active_page()
                assert tab.url == "about:blank"
                assert "INTERNAL-PAGE-CONTENT" not in await tab.content()
            assert internal.paths() == ["/internal"]

    async def test_a_request_that_is_answered_in_time_is_saved(self, downloads_dir: Path) -> None:
        with serve({"/slow": replace(_attachment("a.txt", b"hello"), delay_s=_IN_TIME_S)}) as site:
            async with _session(downloads_dir, local=False, filtered=False) as session:
                result = await session.download_url(url_on("public.test", site, "/slow"))

                assert result is not None
                assert Path(result.path).read_bytes() == b"hello"
