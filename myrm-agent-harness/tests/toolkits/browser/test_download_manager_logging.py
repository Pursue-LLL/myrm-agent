"""Download logs say where a download came from and never the credentials its URL carries.

A download URL is untrusted input and often a signed one: the query holds the signature, the authority may hold a
password, an opaque ``filesystem:`` URL the whole secret. Every line the manager logs about a download names the
scheme, host and path, and none of the parts of a URL that carry a secret: the credentials before the host are
dropped, the query and fragment are replaced by a marker, and what remains is masked before it is cut to the logged
length, so a token that straddles the cut is not left half shown. The reason a refusal gives quotes the URL too, so the URL is
replaced in it by the logged form. A hostile page chooses the URL, so logging it is bounded work however long it is.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.browser.navigation.ssrf_guard import (
    BrowserNavigationBlockedError,
    assert_browser_navigation_allowed,
)
from myrm_agent_harness.toolkits.browser.session.download import manager as download_manager
from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.errors import DownloadError
from myrm_agent_harness.toolkits.browser.session.download.manager import DownloadManager
from myrm_agent_harness.toolkits.browser.session.network import RAW_PREVIEW_WINDOW
from myrm_agent_harness.toolkits.browser.session.network import logger as network_logger
from tests.support.fake_secrets import github_token
from tests.toolkits.browser._download_doubles import download_of

_MANAGER_LOGGER = "myrm_agent_harness.toolkits.browser.session.download.manager"
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


async def _page_starts(manager: DownloadManager, download: MagicMock) -> None:
    """A page starts ``download`` by itself; return once the manager has dealt with it."""
    manager._on_download(download)
    await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)


def _logged_lines(caplog: pytest.LogCaptureFixture, line: str) -> list[str]:
    messages = [record.getMessage() for record in caplog.records if line in record.getMessage()]
    assert messages, f"no log line with {line!r}; logged: {caplog.text!r}"
    return messages


def _assert_names_the_address_only(caplog: pytest.LogCaptureFixture, line: str, *secrets: str) -> None:
    for message in _logged_lines(caplog, line):
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

        with pytest.raises(DownloadError):
            await _manager(tmp_path).download_url(page, _signed())

        _assert_names_the_address_only(caplog, "Failed to download URL")

    @pytest.mark.asyncio
    async def test_a_refused_download_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        verify = AsyncMock(side_effect=BrowserNavigationBlockedError("SSRF blocked: files.example is private"))
        await _page_starts(_manager(tmp_path, verify), download_of(MagicMock(), _signed()))

        _assert_names_the_address_only(caplog, "Refused a download from")

    @pytest.mark.asyncio
    async def test_a_download_that_times_out_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), _signed())
        download.save_as = AsyncMock(side_effect=_never_finishes)

        await _page_starts(_manager(tmp_path, timeout_s=0.05), download)

        _assert_names_the_address_only(caplog, "not saved: saving did not finish")

    @pytest.mark.asyncio
    async def test_a_download_that_cannot_be_saved_logs_no_credentials(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), _signed())
        download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))

        await _page_starts(_manager(tmp_path), download)

        _assert_names_the_address_only(caplog, "not saved: the browser could not save the file")

    @pytest.mark.asyncio
    async def test_a_password_longer_than_the_logged_url_is_never_shown(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), _signed(f"user:{_LONG_PASSWORD}"))
        download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))

        await _page_starts(_manager(tmp_path), download)

        _assert_names_the_address_only(caplog, "not saved", "S3CRET")

    @pytest.mark.asyncio
    async def test_a_token_that_straddles_the_cut_is_masked_whole(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        token = github_token("Ab3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0dF3hJ6")
        # The cut falls four characters into the token: too few for any redactor to recognise it once the text is cut.
        download = download_of(MagicMock(), f"https://files.example/{'x' * 49}/{token}")
        download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))

        await _page_starts(_manager(tmp_path), download)

        (message,) = _logged_lines(caplog, "not saved")
        assert token[:8] not in message
        assert "files.example" in message

    @pytest.mark.asyncio
    async def test_a_long_address_is_cut_to_the_logged_length(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        download = download_of(MagicMock(), f"https://files.example/{'p' * 500}")
        download.save_as = AsyncMock(side_effect=RuntimeError("disk full"))

        await _page_starts(_manager(tmp_path), download)

        (message,) = _logged_lines(caplog, "not saved")
        logged_url = message.removeprefix("Download from ").split(" not saved")[0]
        assert len(logged_url) == download_manager._LOGGED_URL_LENGTH
        assert logged_url.endswith("\u2026")


class TestRefusalOfAHostileUrl:
    """The navigation guard quotes the whole URL in its refusal, and a hostile page chooses that URL."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "url",
        [f"filesystem:https://{_ADDRESS}?sig={_SIGNATURE}", f"ftp://deploy:hunter2@{_ADDRESS}?sig={_SIGNATURE}"],
        ids=["opaque-scheme", "ftp-with-password"],
    )
    async def test_the_refusal_quotes_no_part_of_the_url_that_can_carry_a_secret(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, url: str
    ) -> None:
        manager = _manager(tmp_path, assert_browser_navigation_allowed)

        manager._on_download(download_of(MagicMock(), url))
        await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)

        assert "Unsupported navigation scheme" in caplog.text
        assert _SIGNATURE not in caplog.text
        assert "hunter2" not in caplog.text

    @pytest.mark.asyncio
    async def test_redaction_never_sees_more_than_its_window_of_a_huge_url(self, tmp_path: Path) -> None:
        manager = _manager(tmp_path, assert_browser_navigation_allowed)

        with patch.object(
            network_logger, "redact_sensitive_text", wraps=network_logger.redact_sensitive_text
        ) as redact:
            manager._on_download(download_of(MagicMock(), "filesystem:" + "A" * 200_000))
            await asyncio.gather(*list(manager._pending_tasks), return_exceptions=True)

        assert redact.call_args_list, "the refusal was logged without masking"
        assert max(len(call.args[0]) for call in redact.call_args_list) <= RAW_PREVIEW_WINDOW
