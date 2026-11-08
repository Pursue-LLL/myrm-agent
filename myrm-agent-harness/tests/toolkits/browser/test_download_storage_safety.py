"""DownloadStorage never writes through a link the agent planted, and a download that is not kept leaves nothing behind."""

from __future__ import annotations

import asyncio
import errno
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.browser.session.download.errors import DownloadError
from myrm_agent_harness.toolkits.browser.session.download.storage import DownloadStorage
from tests.toolkits.browser._download_doubles import download_named, kept_files, storage_in

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="creating links needs privileges on Windows")


@POSIX_ONLY
class TestLinksAreNeverFollowed:
    """The sandboxed agent can write the workspace, so it can plant links where the storage will write."""

    @pytest.mark.asyncio
    async def test_a_link_in_place_of_the_downloads_folder_is_refused_and_nothing_is_written_through_it(
        self, tmp_path: Path
    ) -> None:
        hooks = tmp_path / ".git" / "hooks"
        hooks.mkdir(parents=True)
        (tmp_path / ".agent").mkdir()
        (tmp_path / ".agent" / "downloads").symlink_to(hooks)

        with pytest.raises(DownloadError, match=r"downloads folder .* cannot be used because downloads is a link"):
            await storage_in(tmp_path / ".agent" / "downloads", root=tmp_path).save(download_named())

        assert list(hooks.iterdir()) == []

    @pytest.mark.asyncio
    async def test_a_link_in_place_of_a_folder_above_it_is_refused_too(self, tmp_path: Path) -> None:
        workspace = tmp_path / "workspace"
        outside = tmp_path / "outside"
        workspace.mkdir()
        outside.mkdir()
        (workspace / ".agent").symlink_to(outside)

        with pytest.raises(DownloadError, match=r"because \.agent is a link"):
            await storage_in(workspace / ".agent" / "downloads", root=workspace).save(download_named())

        assert list(outside.iterdir()) == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize("plant", ["symlink", "hard-link"])
    async def test_a_link_planted_under_the_file_name_is_left_alone_and_the_download_gets_another_name(
        self, tmp_path: Path, plant: str
    ) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        victim = tmp_path / "victim.txt"
        victim.write_bytes(b"outside")
        if plant == "symlink":
            (directory / "report.pdf").symlink_to(victim)
        else:
            os.link(victim, directory / "report.pdf")

        result = await storage_in(directory).save(download_named(body=b"downloaded"))

        assert result.file_name == "report (1).pdf"
        assert victim.read_bytes() == b"outside"
        assert (directory / "report (1).pdf").read_bytes() == b"downloaded"


class TestNothingIsLeftBehind:
    @pytest.mark.asyncio
    async def test_a_file_type_that_is_not_allowed_is_refused_before_anything_is_created(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        refused_download = download_named(name="setup.exe")

        with pytest.raises(DownloadError, match=r'file type "\.exe" is not allowed'):
            await storage_in(directory).save(refused_download)

        assert not directory.exists()
        refused_download.path.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_hostile_extension_is_quoted_only_in_part(self, tmp_path: Path) -> None:
        with pytest.raises(DownloadError) as refused:
            await storage_in(tmp_path / "dl").save(download_named(name="x." + "e" * 200))

        assert refused.value.reason == f'file type ".{"e" * 16}" is not allowed'

    @pytest.mark.asyncio
    async def test_a_download_the_browser_fails_leaves_no_file_and_keeps_its_words_for_the_log(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "dl"
        download = download_named()
        download.path = AsyncMock(side_effect=RuntimeError("boom"))
        download.failure = AsyncMock(return_value="net::ERR_FAILED")

        with pytest.raises(DownloadError, match="the browser could not save the file") as refused:
            await storage_in(directory).save(download)

        assert "boom" in refused.value.detail
        assert "net::ERR_FAILED" in refused.value.detail
        assert "boom" not in refused.value.reason
        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_download_that_does_not_finish_in_time_leaves_no_file(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        download = download_named()

        async def never_finishes() -> Path:
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        download.path = AsyncMock(side_effect=never_finishes)

        with pytest.raises(DownloadError, match=r"saving did not finish within 0\.05 s"):
            await storage_in(directory, download_timeout_s=0.05).save(download)

        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_save_cancelled_while_the_browser_is_still_downloading_leaves_no_file(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        download = download_named()
        waiting = asyncio.Event()

        async def hangs() -> Path:
            waiting.set()
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        download.path = AsyncMock(side_effect=hangs)
        task = asyncio.create_task(storage_in(directory).save(download))
        await waiting.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_save_cancelled_in_the_middle_of_the_copy_releases_its_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = tmp_path / "dl"
        copying = asyncio.Event()

        async def hangs(_source: Path, fd: int) -> None:
            os.close(fd)
            copying.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(DownloadStorage, "_write", staticmethod(hangs))
        task = asyncio.create_task(storage_in(directory).save(download_named()))
        await copying.wait()
        assert kept_files(directory) == ["report.pdf"]

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_copy_the_disk_refuses_leaves_no_file_and_is_reported(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        directory = tmp_path / "dl"

        async def disk_full(_source: Path, fd: int) -> None:
            os.close(fd)
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(DownloadStorage, "_write", staticmethod(disk_full))

        with pytest.raises(DownloadError, match="could not be copied into the downloads folder") as refused:
            await storage_in(directory).save(download_named())

        assert "No space left on device" in refused.value.detail
        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_file_that_vanishes_before_it_is_copied_is_reported(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        download = download_named()
        download.path = AsyncMock(return_value=tmp_path / "gone-from-the-browsers-temp-dir")

        with pytest.raises(DownloadError, match="the downloaded file disappeared"):
            await storage_in(directory).save(download)

        assert kept_files(directory) == []
