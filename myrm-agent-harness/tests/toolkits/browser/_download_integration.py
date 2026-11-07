"""Real-Chromium session and probes shared by the download integration tests.

[INPUT]
- toolkits.browser::BrowserSession (POS: the aggregate root every browser tool talks to)
- toolkits.browser.pool::GlobalBrowserPool, BrowserPoolConfig, ContextType (POS: browser process pool, its settings, and the context kind a session runs in)
- toolkits.browser.session.download_config::DownloadConfig (POS: where a download manager keeps files, how much, for how long, and which kinds)
- tests.toolkits.browser._fake_dns::launch_options_dialing_loopback (POS: Chromium launch options that connect fake hostnames to loopback)
- tests.toolkits.browser._redirect_servers::Reply (POS: one scripted response of a loopback test server)

[OUTPUT]
- DNS_ANSWERS: the fake hostnames the process resolver answers (``public.test`` is public, ``meta.test`` is cloud metadata)
- DOWNLOAD_TIMEOUT_S / SETTLE_S: how long a session and a probe wait for a download, and how long a test lets the browser settle
- attachment / SECRET_FILE: scripted replies that make the browser download a body
- open_session: a session with one tab, with or without download support, local or cloud mode, with or without a request filter
- point_browser_tmpdir: points the temp dir the browser driver keeps downloads in at a directory of the test
- saved_names / kept_by_browser / kept_by_browser_once_settled: what a session saved, and what the browser still holds
  of its downloads (right now, or once it has finished discarding)
- start_page_navigation: navigates the page the way a script or a link does, not through ``download_url``
- until: waits for a condition under a deadline

[POS]
Test support for ``test_download_url_integration`` (requests the agent makes) and
``test_download_page_started_integration`` (downloads a page starts itself): one way to open a real session and one
way to read what the browser still keeps, so both prove their claims with the same probes. A probe that finds nothing
proves nothing unless it can see something: ``test_download_page_started_integration`` shows it a body that is still
arriving.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser import BrowserSession
from myrm_agent_harness.toolkits.browser.pool import BrowserPoolConfig, ContextType, GlobalBrowserPool
from myrm_agent_harness.toolkits.browser.session.download_config import DownloadConfig
from tests.toolkits.browser._fake_dns import launch_options_dialing_loopback
from tests.toolkits.browser._redirect_servers import Reply

DNS_ANSWERS = {"public.test": "93.184.216.34", "meta.test": "169.254.169.254"}
DOWNLOAD_TIMEOUT_S = 10.0
SETTLE_S = 0.5

_START_NAVIGATION_JS = "(url) => { window.location.href = url; }"


def attachment(name: str, body: bytes) -> Reply:
    return Reply(
        body=body,
        content_type="text/plain",
        headers=(("Content-Disposition", f'attachment; filename="{name}"'),),
    )


SECRET_FILE = attachment("secret.txt", b"INTERNAL-SECRET")


@asynccontextmanager
async def open_session(
    downloads_dir: Path | None, *, local: bool, filtered: bool = True
) -> AsyncIterator[BrowserSession]:
    """A session with one tab; it has download support only when ``downloads_dir`` is given.

    ``filtered=False`` leaves its context without a request filter.
    """
    pool = GlobalBrowserPool(
        max_browsers=1,
        config=None if filtered else BrowserPoolConfig.minimal(),
        launch_options=launch_options_dialing_loopback(DNS_ANSWERS),
    )
    download_config = (
        DownloadConfig(downloads_dir=downloads_dir, download_timeout_s=DOWNLOAD_TIMEOUT_S)
        if downloads_dir is not None
        else None
    )
    session = BrowserSession(pool, ContextType.AGENT, allow_private_networks=local, download_config=download_config)
    try:
        await session.new_tab()
        yield session
    finally:
        await session.close()
        await pool.shutdown()


def point_browser_tmpdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The temp dir the browser driver keeps downloads in; it is read when the browser starts, so it is set first."""
    directory = tmp_path / "browser-tmp"
    directory.mkdir()
    monkeypatch.setenv("TMPDIR", str(directory))
    return directory


def saved_names(downloads_dir: Path) -> list[str]:
    return sorted(path.name for path in downloads_dir.iterdir())


def kept_by_browser(browser_tmp: Path) -> list[str]:
    """What the browser still holds of its downloads: a refused or abandoned one leaves nothing here."""
    return sorted(path.name for path in browser_tmp.glob("*artifacts*/*"))


async def start_page_navigation(session: BrowserSession, url: str) -> None:
    """Navigate the page the way a script or a link does, not through ``download_url``."""
    await session.get_active_page().evaluate(_START_NAVIGATION_JS, url)


async def until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(DOWNLOAD_TIMEOUT_S):
        while not condition():
            await asyncio.sleep(0.05)


async def kept_by_browser_once_settled(browser_tmp: Path) -> list[str]:
    """``kept_by_browser`` after the browser has finished discarding; that can lag behind the verdict.

    Call it only after the download has started: an empty directory proves nothing before there is a body to keep.
    """
    with suppress(TimeoutError):
        await until(lambda: not kept_by_browser(browser_tmp))
    return kept_by_browser(browser_tmp)
