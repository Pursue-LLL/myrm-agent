"""Unit tests for DownloadManager — full coverage with mocks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.pool import ContextType
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.errors import DownloadError
from myrm_agent_harness.toolkits.browser.session.download.manager import DownloadManager
from myrm_agent_harness.toolkits.browser.session.download.records import DownloadResult
from tests.toolkits.browser._download_doubles import ExpectDownload, finished_file

# =============================================================================
# Fixtures
# =============================================================================


async def _allow_every_address(_url: str) -> None:
    """The verifier of a manager that is under test for something other than address policy."""


@pytest.fixture
def tmp_downloads(tmp_path: Path) -> Path:
    dl_dir = tmp_path / "downloads"
    dl_dir.mkdir()
    return dl_dir


@pytest.fixture
def config(tmp_downloads: Path) -> DownloadConfig:
    return DownloadConfig(
        downloads_dir=tmp_downloads,
        confined_to=tmp_downloads.parent,
        max_file_size_mb=1,
        download_timeout_s=5.0,
        max_concurrent_downloads=2,
    )


@pytest.fixture
def manager(config: DownloadConfig) -> DownloadManager:
    return DownloadManager(config, verify_final_url=_allow_every_address)


def _make_download_mock(
    url: str = "https://example.com/file.pdf",
    suggested_filename: str = "file.pdf",
    *,
    save_content: bytes = b"%PDF-fake-content",
    failure_msg: str | None = None,
) -> MagicMock:
    """Create a mock Patchright Download object."""
    dl = MagicMock()
    dl.url = url
    dl.suggested_filename = suggested_filename
    dl.failure = AsyncMock(return_value=failure_msg)
    dl.cancel = AsyncMock()
    dl.delete = AsyncMock()

    async def _path() -> Path:
        if failure_msg:
            raise RuntimeError(failure_msg)
        return finished_file(save_content)

    dl.path = AsyncMock(side_effect=_path)
    return dl


def _make_page_mock() -> MagicMock:
    page = MagicMock()
    page.url = "https://example.com/report.pdf"
    page.evaluate = AsyncMock(return_value=None)
    page.on = MagicMock()
    return page


# =============================================================================
# DownloadResult tests
# =============================================================================


class TestDownloadResult:
    def test_result_frozen(self) -> None:
        result = DownloadResult(
            url="https://x.com/f.pdf",
            path="/tmp/f.pdf",
            file_name="f.pdf",
            file_size=1024,
            file_type="pdf",
        )
        assert result.url == "https://x.com/f.pdf"
        with pytest.raises(AttributeError):
            result.file_name = "other"  # type: ignore[misc]


# =============================================================================
# DownloadManager core tests
# =============================================================================


class TestDownloadManagerInit:
    def test_init_touches_no_disk(self, tmp_path: Path) -> None:
        """A workspace whose chats never download gets no downloads directory."""
        dl_dir = tmp_path / "new_dir" / "nested"
        DownloadManager(
            DownloadConfig(downloads_dir=dl_dir, confined_to=tmp_path), verify_final_url=_allow_every_address
        )
        assert not dl_dir.exists()

    def test_a_new_manager_has_saved_and_refused_nothing(self, tmp_path: Path) -> None:
        dm = DownloadManager(
            DownloadConfig(downloads_dir=tmp_path / "downloads", confined_to=tmp_path),
            verify_final_url=_allow_every_address,
        )

        assert dm.downloads == []
        assert dm.refusals == ()


class TestDownloadManagerAttach:
    def test_attach_registers_listener(self, manager: DownloadManager) -> None:
        page = _make_page_mock()
        manager.attach(page)
        page.on.assert_called_once()
        assert page.on.call_args[0][0] == "download"

    def test_attach_idempotent_same_page(self, manager: DownloadManager) -> None:
        """Same page object attached twice should only register listener once."""
        page = _make_page_mock()
        manager.attach(page)
        manager.attach(page)
        page.on.assert_called_once()

    def test_attach_different_pages(self, manager: DownloadManager) -> None:
        """Different pages should each get their own listener."""
        page1 = _make_page_mock()
        page2 = _make_page_mock()
        manager.attach(page1)
        manager.attach(page2)
        assert page1.on.call_count == 1
        assert page2.on.call_count == 1


class TestDownloadManagerProcessDownload:
    @pytest.mark.asyncio
    async def test_successful_download(self, manager: DownloadManager) -> None:
        dl = _make_download_mock()
        result = await manager._process_download(dl)

        assert result.file_name == "file.pdf"
        assert result.file_type == "pdf"
        assert Path(result.path).exists()
        assert manager.downloads == [result]

    @pytest.mark.asyncio
    async def test_disallowed_extension_rejected(self, tmp_downloads: Path) -> None:
        cfg = DownloadConfig(
            downloads_dir=tmp_downloads,
            confined_to=tmp_downloads.parent,
            allowed_extensions=frozenset({"pdf"}),
        )
        dm = DownloadManager(cfg, verify_final_url=_allow_every_address)
        dl = _make_download_mock(
            url="https://x.com/malware.exe",
            suggested_filename="malware.exe",
        )
        with pytest.raises(DownloadError, match=r'file type "\.exe" is not allowed'):
            await dm._process_download(dl)
        dl.cancel.assert_awaited_once()
        dl.delete.assert_awaited_once()  # a body that already finished is not left in the browser's temp dir

    @pytest.mark.asyncio
    async def test_file_size_exceeded(self, tmp_downloads: Path) -> None:
        cfg = DownloadConfig(
            downloads_dir=tmp_downloads,
            confined_to=tmp_downloads.parent,
            max_file_size_mb=0,  # 0 MB limit — any file exceeds
        )
        dm = DownloadManager(cfg, verify_final_url=_allow_every_address)
        dl = _make_download_mock(save_content=b"some content")
        with pytest.raises(DownloadError, match="larger than 0 MB"):
            await dm._process_download(dl)

    @pytest.mark.asyncio
    async def test_save_failure(self, manager: DownloadManager) -> None:
        dl = _make_download_mock(failure_msg="network error")
        with pytest.raises(DownloadError, match="could not save"):
            await manager._process_download(dl)
        assert manager.downloads == []

    @pytest.mark.asyncio
    async def test_downloads_with_one_name_are_saved_under_distinct_names(self, manager: DownloadManager) -> None:
        r1 = await manager._process_download(_make_download_mock())
        r2 = await manager._process_download(_make_download_mock())

        assert r1.file_name == "file.pdf"
        assert r2.file_name == "file (1).pdf"
        assert len(manager.downloads) == 2


# =============================================================================
# download_url tests
# =============================================================================


class TestDownloadUrl:
    @pytest.mark.asyncio
    async def test_download_url_success(self, manager: DownloadManager) -> None:
        page = _make_page_mock()
        download_mock = _make_download_mock(url="https://x.com/data.csv", suggested_filename="data.csv")
        page.expect_download = lambda **_kw: ExpectDownload(download_mock)

        result = await manager.download_url(page, "https://x.com/data.csv")
        assert result.file_name == "data.csv"

    @pytest.mark.asyncio
    async def test_download_url_asks_the_page_again_for_a_url_it_saved_before(self, manager: DownloadManager) -> None:
        """What a URL serves can change: a file kept from an earlier request must not stand in for the new one."""
        page = _make_page_mock()
        served = [
            _make_download_mock(url="https://x.com/f.pdf", suggested_filename="f.pdf", save_content=b"first"),
            _make_download_mock(url="https://x.com/f.pdf", suggested_filename="f.pdf", save_content=b"second"),
        ]
        page.expect_download = lambda **_kw: ExpectDownload(served.pop(0))

        first = await manager.download_url(page, "https://x.com/f.pdf")
        second = await manager.download_url(page, "https://x.com/f.pdf")

        assert page.evaluate.await_count == 2
        assert (Path(first.path).read_bytes(), Path(second.path).read_bytes()) == (b"first", b"second")
        assert second.file_name == "f (1).pdf"

    @pytest.mark.asyncio
    async def test_download_url_failure_says_why(self, manager: DownloadManager) -> None:
        page = _make_page_mock()
        page.expect_download = MagicMock(side_effect=Exception("error"))

        with pytest.raises(DownloadError, match="could not complete the download"):
            await manager.download_url(page, "https://x.com/broken")

    @pytest.mark.asyncio
    async def test_download_url_that_starts_no_download_says_it_timed_out(self, manager: DownloadManager) -> None:
        page = _make_page_mock()
        page.expect_download = MagicMock(side_effect=TimeoutError("no download started"))

        with pytest.raises(DownloadError, match=r"no download started within 5 s \(the address may open a page"):
            await manager.download_url(page, "https://x.com/page", timeout=5.0)


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_cancels_pending(self, manager: DownloadManager) -> None:
        task = MagicMock()
        task.done.return_value = False
        task.cancel = MagicMock()
        manager._pending_tasks.add(task)

        with patch("asyncio.gather", new_callable=AsyncMock):
            await manager.cleanup()

        task.cancel.assert_called_once()
        assert len(manager._pending_tasks) == 0

    @pytest.mark.asyncio
    async def test_cleanup_empty(self, manager: DownloadManager) -> None:
        await manager.cleanup()
        assert len(manager._pending_tasks) == 0


class TestOnDownload:
    @pytest.mark.asyncio
    async def test_on_download_creates_task(self, manager: DownloadManager) -> None:
        dl = _make_download_mock()
        manager._on_download(dl)
        assert len(manager._pending_tasks) >= 1
        await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)
        assert len(manager.downloads) == 1

    @pytest.mark.asyncio
    async def test_on_download_error_handled(self, manager: DownloadManager) -> None:
        dl = _make_download_mock(failure_msg="fail")
        manager._on_download(dl)
        await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)
        assert len(manager.downloads) == 0


# =============================================================================
# Integration: BrowserSession download delegation
# =============================================================================


class TestBrowserSessionDownloadIntegration:
    def test_list_downloads_no_manager(self) -> None:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        pool = MagicMock()
        session = BrowserSession(pool, ContextType.AGENT)
        assert session.list_downloads() == []

    def test_list_downloads_with_manager(self, tmp_downloads: Path) -> None:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        pool = MagicMock()
        cfg = DownloadConfig(downloads_dir=tmp_downloads, confined_to=tmp_downloads.parent)
        session = BrowserSession(pool, ContextType.AGENT, download_config=cfg)
        assert session.list_downloads() == []
        assert session._download_manager is not None

    @pytest.mark.parametrize("configured", [True, False], ids=["with-manager", "without-manager"])
    def test_the_browser_context_accepts_downloads_only_when_a_manager_judges_them(
        self, tmp_downloads: Path, configured: bool
    ) -> None:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        config = DownloadConfig(downloads_dir=tmp_downloads, confined_to=tmp_downloads.parent) if configured else None
        session = BrowserSession(MagicMock(), ContextType.AGENT, download_config=config)

        context_kwargs = session._tab_controller._context_kwargs
        assert context_kwargs is not None
        assert context_kwargs["accept_downloads"] is configured

    @pytest.mark.asyncio
    async def test_download_url_no_manager_raises(self) -> None:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        pool = MagicMock()
        session = BrowserSession(pool, ContextType.AGENT)
        with pytest.raises(RuntimeError, match="Download support not enabled"):
            await session.download_url("https://x.com/f.pdf")

    @pytest.mark.asyncio
    async def test_the_manager_judges_every_download_with_the_navigator_of_the_session(
        self, tmp_downloads: Path
    ) -> None:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        config = DownloadConfig(downloads_dir=tmp_downloads, confined_to=tmp_downloads.parent)
        session = BrowserSession(MagicMock(), ContextType.AGENT, download_config=config)
        navigator = MagicMock()
        navigator.assert_landed_allowed = AsyncMock()
        session._navigator = navigator
        assert session._download_manager is not None

        await session._download_manager._verify_final_url("https://cdn.example/a.pdf")

        navigator.assert_landed_allowed.assert_awaited_once_with("https://cdn.example/a.pdf")

    def test_stats_includes_downloads(self, tmp_downloads: Path) -> None:
        from myrm_agent_harness.toolkits.browser.session import BrowserSession

        pool = MagicMock()
        cfg = DownloadConfig(downloads_dir=tmp_downloads, confined_to=tmp_downloads.parent)
        session = BrowserSession(pool, ContextType.AGENT, download_config=cfg)
        stats = session.stats
        assert "downloads" in stats
        assert stats["downloads"] == 0
