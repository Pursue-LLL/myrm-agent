"""Real-Chromium proof that a pooled context refuses downloads unless its owner asks for them.

Left to its default the browser saves every download a page starts into its temp dir and holds it there until the
context closes. A context whose owner registers nobody to judge downloads (the browser fetcher of ``web_fetch`` takes a
CRAWL page from the pool that way) must therefore refuse them itself. The probe is what the browser still holds of its
downloads, read from the temp dir its driver keeps them in; the opted-in context shows it can see a kept file.
Run with: `pytest -m integration tests/toolkits/browser/pool/test_context_download_default_integration.py`.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser.pool import ContextType, GlobalBrowserPool
from tests.toolkits.browser._browser_available import chromium_available
from tests.toolkits.browser._download_integration import (
    SETTLE_S,
    attachment,
    kept_by_browser,
    navigate_by_script,
    open_pool,
    point_browser_tmpdir,
    until,
)
from tests.toolkits.browser._redirect_servers import serve

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.skipif(not chromium_available(), reason="Chromium not available"),
]


@pytest.fixture
def browser_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    return point_browser_tmpdir(tmp_path, monkeypatch)


async def _page_starts_a_download(
    pool: GlobalBrowserPool, url: str, *, context_type: ContextType, context_kwargs: dict[str, object] | None
) -> None:
    """Take a page from the pool, let it start the download at ``url`` and give the browser time to keep it."""
    page, context_key = await pool.acquire_page(
        context_type, context_key=f"{context_type.value}-probe", context_kwargs=context_kwargs
    )
    try:
        started: list[str] = []
        page.on("download", lambda download: started.append(download.url))
        await navigate_by_script(page, url)
        await until(lambda: bool(started))  # the page did start a download
        await asyncio.sleep(SETTLE_S)
    finally:
        await pool.release_page(page, context_key)


class TestPooledContextDownloadDefault:
    @pytest.mark.parametrize("context_type", [ContextType.CRAWL, ContextType.AGENT], ids=["crawl", "agent"])
    async def test_a_context_nobody_judges_downloads_for_keeps_none(
        self, browser_tmp: Path, context_type: ContextType
    ) -> None:
        with serve({"/file": attachment("a.txt", b"hello")}) as site:
            async with open_pool(filtered=False) as pool:
                await _page_starts_a_download(pool, site.url("/file"), context_type=context_type, context_kwargs=None)

                assert kept_by_browser(browser_tmp) == []

    async def test_a_context_whose_owner_asks_for_downloads_keeps_them(self, browser_tmp: Path) -> None:
        # The control: the probe sees a file when the browser is allowed to keep it.
        with serve({"/file": attachment("a.txt", b"hello")}) as site:
            async with open_pool(filtered=False) as pool:
                await _page_starts_a_download(
                    pool,
                    site.url("/file"),
                    context_type=ContextType.AGENT,
                    context_kwargs={"accept_downloads": True},
                )

                assert len(kept_by_browser(browser_tmp)) == 1
