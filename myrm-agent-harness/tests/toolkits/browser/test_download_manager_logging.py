"""Download logs say where a download came from and never the credentials its URL carries.

A download URL is untrusted input and often a signed one: the query holds the signature, the authority may hold a
password. Every line the manager logs about a download names the scheme, host and path, and nothing a URL can carry
as a secret; a password is masked before the URL is cut to the logged length, so a long one cannot slip through half
cut off.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import BrowserNavigationBlockedError
from myrm_agent_harness.toolkits.browser.session import download_manager
from myrm_agent_harness.toolkits.browser.session.download_config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download_manager import DownloadManager
from tests.toolkits.browser._download_doubles import download_of

_MANAGER_LOGGER = "myrm_agent_harness.toolkits.browser.session.download_manager"
_SIGNATURE = "SIGNATURE-VALUE"
_FRAGMENT = "frag-9f3"
_LONG_PASSWORD = "S3CRET" + "x" * 90  # longer than the logged URL, so the cut falls inside it
_ADDRESS = "files.example/report.zip"


def _signed(userinfo: str = "user:hunter2") -> str:
    return f"https://{userinfo}@{_ADDRESS}?sv=2024-01-01&sig={_SIGNATURE}#{_FRAGMENT}"


@pytest.fixture(autouse=True)
def _capture_warnings(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger=_MANAGER_LOGGER)


@pytest.fixture(autouse=True)
def _no_navigation_to_stop() -> Iterator[None]:
    with patch.object(download_manager, "abort_pending_navigation", new_callable=AsyncMock):
        yield


def _manager(tmp_path: Path, verify: AsyncMock | None = None, *, timeout_s: float = 5.0) -> DownloadManager:
    config = DownloadConfig(downloads_dir=tmp_path / "downloads", download_timeout_s=timeout_s)
    return DownloadManager(config, verify_final_url=verify or AsyncMock())


async def _never_finishes(_path: str) -> None:
    await asyncio.sleep(3600)


def _assert_names_the_address_only(caplog: pytest.LogCaptureFixture, line: str, *secrets: str) -> None:
    messages = [record.getMessage() for record in caplog.records if line in record.getMessage()]
    assert messages, f"no log line with {line!r}; logged: {caplog.text!r}"
    for message in messages:
        assert _ADDRESS in message
        for secret in ("hunter2", _SIGNATURE, "sv=2024-01-01", _FRAGMENT, *secrets):
            assert secret not in message


class TestDownloadLogs:
    @pytest.mark.asyncio
    async def test_a_request_that_fails_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        page = MagicMock()
        page.evaluate = AsyncMock()
        page.expect_download = MagicMock(side_effect=RuntimeError("browser gone"))

        assert await _manager(tmp_path).download_url(page, _signed()) is None

        _assert_names_the_address_only(caplog, "Failed to download URL")

    @pytest.mark.asyncio
    async def test_a_refused_download_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        verify = AsyncMock(side_effect=BrowserNavigationBlockedError("SSRF blocked: files.example is private"))
        manager = _manager(tmp_path, verify)

        manager._on_download(download_of(MagicMock(), _signed()))
        await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)

        _assert_names_the_address_only(caplog, "Refused a download from")

    @pytest.mark.asyncio
    async def test_a_download_that_times_out_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), _signed())
        download.save_as = AsyncMock(side_effect=_never_finishes)

        assert await _manager(tmp_path, timeout_s=0.05)._process_download(download) is None

        _assert_names_the_address_only(caplog, "Download timed out")

    @pytest.mark.asyncio
    async def test_a_download_that_cannot_be_saved_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), _signed())
        download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))

        assert await _manager(tmp_path)._process_download(download) is None

        _assert_names_the_address_only(caplog, "Download failed for")

    @pytest.mark.asyncio
    async def test_a_long_password_is_masked_before_the_url_is_cut(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), _signed(f"user:{_LONG_PASSWORD}"))
        download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))

        await _manager(tmp_path)._process_download(download)

        _assert_names_the_address_only(caplog, "Download failed for", "S3CRET")
