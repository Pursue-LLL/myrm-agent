"""Real-Chromium proof that a download a page starts itself is judged at the address it came from.

A download from a script or a link reaches the page's listener, which judges it like one the agent asked for: a refused
one is cancelled and deleted, also while its body is still arriving, and nothing of it is kept; one that passes is
saved once and the browser keeps nothing of it afterwards. A request the agent makes takes only the first download its
page starts, so a second one that starts while the request waits is judged like any other. A session without download
support has nothing to judge a download with, so its browser cancels the download. The hosts are fake: the process
resolver answers ``public.test`` with a public address and ``meta.test`` with the metadata address while Chromium
connects both to the loopback test servers, so a request the policy lets through lands for real and one it refuses is
proven by the server never hearing of it (see ``test_download_url_integration`` for the requests the agent makes). What
the browser still holds of a download is read from the temp dir its driver keeps downloads in, which each test points at
its own directory.
Run with: `pytest -m integration tests/toolkits/browser/test_download_page_started_integration.py`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import replace
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession, enhancers
from myrm_agent_harness.toolkits.browser.session.download import DownloadResult
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_doubles import kept_files
from tests.toolkits.browser._download_integration import (
    DNS_ANSWERS,
    DOWNLOAD_TIMEOUT_S,
    SECRET_FILE,
    SETTLE_S,
    attachment,
    delay_verdicts,
    kept_by_browser,
    kept_by_browser_once_settled,
    open_session,
    point_browser_tmpdir,
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

# How long the verdict on a download is held back, so a small body is fully written before the verdict arrives.
_LATE_VERDICT_S = 1.0
# A body that stalls: the server sends enough for the browser to start the download (a few bytes of plain text are
# held back for content sniffing), promises far more, and holds the connection open longer than any wait in these
# tests, so the download is still in progress whenever it is looked at.
_STALLED_BODY = b"INTERNAL-SECRET" * 512
_STALLED_BODY_LENGTH = 1_000_000
_STALL_S = 2 * DOWNLOAD_TIMEOUT_S

_CLICK_BLOB_DOWNLOAD_JS = """() => {
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob(['made-in-page'], { type: 'text/plain' }));
    link.download = 'made.txt';
    document.body.appendChild(link);
    link.click();
}"""


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


async def _until_judged(session: BrowserSession, caplog: pytest.LogCaptureFixture) -> None:
    """Wait for the verdict on a download the page started: refused (the manager logs it) or saved."""
    await until(lambda: "Refused a download" in caplog.text or bool(session.list_downloads()))


async def _page_starts_a_download_while_a_request_waits(
    session: BrowserSession, asked: list[str], requested_url: str, started_url: str
) -> DownloadResult:
    """Request ``requested_url``; while it waits on its verdict, the page starts a download from ``started_url``.

    Returns the request's result once the second download has got its verdict request too.
    """
    started: list[str] = []
    session.get_active_page().on("download", lambda download: started.append(download.url))
    request = asyncio.create_task(session.download_url(requested_url))
    await until(lambda: len(asked) == 1)  # the request's download is being judged: the request still waits
    await start_page_navigation(session, started_url)
    await until(lambda: len(started) == 2)
    assert not request.done(), "the second download started after the request had ended"
    result = await request
    with suppress(TimeoutError):
        await until(lambda: len(asked) == 2)
    assert len(asked) == 2, "the second download of the page got no verdict"
    return result


class TestDownloadsThePageStartsItself:
    """A download from a script or a link reaches the page's listener, which judges it like a request."""

    async def test_a_download_from_a_metadata_hostname_is_discarded_and_nothing_is_kept(
        self, downloads_dir: Path, browser_tmp: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with serve({"/home": page("home")}) as site, serve({"/creds": SECRET_FILE}) as service:
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await start_page_navigation(session, url_on("meta.test", service, "/creds"))
                await _until_judged(session, caplog)

                assert session.list_downloads() == []
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == []
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
            delay_verdicts(monkeypatch, verdict_delay_s)
        with (
            serve({"/secret.txt": SECRET_FILE}) as internal,
            serve({"/home": page("home"), "/go": redirect(internal.url("/secret.txt"))}) as site,
        ):
            async with open_session(downloads_dir, local=False, filtered=filtered) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await start_page_navigation(session, url_on("public.test", site, "/go"))
                await _until_judged(session, caplog)

                assert session.list_downloads() == []
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == []
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
        delay_verdicts(monkeypatch, _LATE_VERDICT_S)
        stalled_secret = replace(
            attachment("secret.txt", _STALLED_BODY), declared_length=_STALLED_BODY_LENGTH, hold_open_s=_STALL_S
        )
        with serve({"/home": page("home")}) as site, serve({"/creds": stalled_secret}) as service:
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await start_page_navigation(session, url_on("meta.test", service, "/creds"))
                await until(lambda: bool(kept_by_browser(browser_tmp)))  # the probe sees the body arriving
                await _until_judged(session, caplog)

                assert session.list_downloads() == []
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == []

    @pytest.mark.parametrize("filtered", [True, False], ids=["filtered", "unfiltered"])
    async def test_a_public_download_is_saved_once_and_the_browser_keeps_nothing_of_it(
        self, downloads_dir: Path, browser_tmp: Path, filtered: bool
    ) -> None:
        with serve({"/home": page("home"), "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False, filtered=filtered) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await start_page_navigation(session, url_on("public.test", site, "/file"))
                await until(lambda: bool(session.list_downloads()))

                assert [Path(saved.path).read_bytes() for saved in session.list_downloads()] == [b"hello"]
                assert await kept_by_browser_once_settled(browser_tmp) == []  # the saved copy is the only one
            assert kept_files(downloads_dir) == ["a.txt"]

    async def test_a_download_the_page_builds_itself_names_no_address_and_is_saved(self, downloads_dir: Path) -> None:
        with serve({"/home": page("home")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                await session.get_active_page().evaluate(_CLICK_BLOB_DOWNLOAD_JS)
                await until(lambda: bool(session.list_downloads()))

                assert [Path(saved.path).read_bytes() for saved in session.list_downloads()] == [b"made-in-page"]


class TestDownloadsWhileARequestWaits:
    """A request takes the first download its page starts; a second one still gets its verdict."""

    async def test_a_second_public_download_is_saved_next_to_the_requested_one(
        self, downloads_dir: Path, browser_tmp: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = delay_verdicts(monkeypatch, _LATE_VERDICT_S)
        with (
            serve({"/home": page("home"), "/first": attachment("first.txt", b"first")}) as site,
            serve({"/second": attachment("second.txt", b"second")}) as other,
        ):
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                result = await _page_starts_a_download_while_a_request_waits(
                    session, asked, url_on("public.test", site, "/first"), url_on("public.test", other, "/second")
                )
                await until(lambda: len(session.list_downloads()) == 2)

                assert result is not None
                assert sorted(Path(saved.path).read_bytes() for saved in session.list_downloads()) == [
                    b"first",
                    b"second",
                ]
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == ["first.txt", "second.txt"]

    async def test_a_second_download_from_a_metadata_hostname_is_discarded_and_nothing_is_kept(
        self,
        downloads_dir: Path,
        browser_tmp: Path,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        asked = delay_verdicts(monkeypatch, _LATE_VERDICT_S)
        with (
            serve({"/home": page("home"), "/first": attachment("first.txt", b"first")}) as site,
            serve({"/creds": SECRET_FILE}) as service,
        ):
            async with open_session(downloads_dir, local=False, filtered=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))

                result = await _page_starts_a_download_while_a_request_waits(
                    session, asked, url_on("public.test", site, "/first"), url_on("meta.test", service, "/creds")
                )
                await until(lambda: "Refused a download" in caplog.text)

                assert result is not None
                assert [Path(saved.path).read_bytes() for saved in session.list_downloads()] == [b"first"]
                assert await kept_by_browser_once_settled(browser_tmp) == []
            assert kept_files(downloads_dir) == ["first.txt"]
            assert service.hits == [("GET", "/creds")]  # only keeping the body is refused; the request was made


class TestTheReportOfAnAction:
    """What an action came to waits for the downloads it started, not for one that was already being judged."""

    async def test_it_does_not_wait_for_a_download_that_started_before_the_action(
        self, downloads_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        asked = delay_verdicts(monkeypatch, _LATE_VERDICT_S)
        with serve({"/home": page("home"), "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(downloads_dir, local=False) as session:
                await session.navigate(url_on("public.test", site, "/home"))
                await start_page_navigation(session, url_on("public.test", site, "/file"))
                await until(lambda: len(asked) == 1)  # being judged: its verdict is held back

                started = time.monotonic()
                activity = await session.downloads_since(session.download_mark())

                assert time.monotonic() - started < _LATE_VERDICT_S / 2
                assert activity.saved == ()
                await until(lambda: bool(session.list_downloads()))  # judged later, it is still saved


class TestWithoutDownloadSupport:
    """A session with no download manager has nothing to judge a download with, so its browser keeps none."""

    @pytest.mark.parametrize("filtered", [True, False], ids=["filtered", "unfiltered"])
    async def test_a_download_the_page_starts_is_cancelled_and_nothing_is_kept(
        self, browser_tmp: Path, filtered: bool
    ) -> None:
        with serve({"/home": page("home"), "/file": attachment("a.txt", b"hello")}) as site:
            async with open_session(None, local=False, filtered=filtered) as session:
                started: list[str] = []
                session.get_active_page().on("download", lambda download: started.append(download.url))
                await session.navigate(url_on("public.test", site, "/home"))

                await start_page_navigation(session, url_on("public.test", site, "/file"))
                await until(lambda: bool(started))  # the page did start a download
                await asyncio.sleep(SETTLE_S)

                assert kept_by_browser(browser_tmp) == []
                assert session.list_downloads() == []
