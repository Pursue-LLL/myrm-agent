"""DownloadStorage: a unique name per download, the directory's quota, and nothing left behind by one that is not kept."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.browser.session.download.config import DownloadConfig
from myrm_agent_harness.toolkits.browser.session.download.errors import DownloadError
from myrm_agent_harness.toolkits.browser.session.download.storage import DownloadStorage, sanitize_filename
from tests.toolkits.browser._download_doubles import download_of, kept_files

_MIB = 1024 * 1024
_URL = "https://files.example/report.pdf"
_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


def _storage(
    directory: Path,
    *,
    max_files: int = 200,
    max_total_mb: int = 1024,
    max_file_size_mb: int = 100,
    download_timeout_s: float = 5.0,
) -> DownloadStorage:
    return DownloadStorage(
        DownloadConfig(
            downloads_dir=directory,
            max_files=max_files,
            max_total_mb=max_total_mb,
            max_file_size_mb=max_file_size_mb,
            download_timeout_s=download_timeout_s,
        )
    )


def _download(name: str = "report.pdf", body: bytes = b"data") -> MagicMock:
    return download_of(MagicMock(), _URL, name=name, body=body)


class TestSanitizeFilename:
    @pytest.mark.parametrize(
        ("input_name", "expected"),
        [
            ("normal.pdf", "normal.pdf"),
            ("../../etc/passwd", "passwd"),
            ("file<name>.txt", "file_name_.txt"),
            (" . . ", "download"),
            ("file:with:colons.doc", "file_with_colons.doc"),
        ],
    )
    def test_sanitize_filename(self, input_name: str, expected: str) -> None:
        assert sanitize_filename(input_name) == expected


class TestNames:
    @pytest.mark.asyncio
    async def test_downloads_with_one_name_are_saved_under_distinct_names(self, tmp_path: Path) -> None:
        storage = _storage(tmp_path / "dl")

        names = [(await storage.save(_download())).file_name for _ in range(3)]

        assert names == ["report.pdf", "report (1).pdf", "report (2).pdf"]

    @pytest.mark.asyncio
    async def test_downloads_saving_at_the_same_moment_each_get_their_own_file(self, tmp_path: Path) -> None:
        """The browser writes only after the name is taken, so every claim happens before any write."""
        storage = _storage(tmp_path / "dl")
        count = 5
        entered = 0
        every_name_taken = asyncio.Event()

        def gated(index: int) -> MagicMock:
            download = _download()

            async def save_as(path: str) -> None:
                nonlocal entered
                entered += 1
                if entered == count:
                    every_name_taken.set()
                await every_name_taken.wait()
                Path(path).write_bytes(f"body-{index}".encode())

            download.save_as = AsyncMock(side_effect=save_as)
            return download

        results = await asyncio.gather(*(storage.save(gated(i)) for i in range(count)))

        assert len({result.file_name for result in results}) == count
        for index, result in enumerate(results):
            assert Path(result.path).read_bytes() == f"body-{index}".encode()

    @pytest.mark.asyncio
    async def test_a_file_without_extension_is_kept_without_a_type(self, tmp_path: Path) -> None:
        result = await _storage(tmp_path / "dl").save(_download(name="README"))

        assert (result.file_name, result.file_type) == ("README", None)

    @pytest.mark.asyncio
    async def test_a_saved_file_has_the_mode_of_a_new_file(self, tmp_path: Path) -> None:
        """The browser keeps the mode of the file it overwrites, so the claimed name must not be more private."""
        directory = tmp_path / "dl"
        result = await _storage(directory).save(_download())

        fresh = directory / "fresh"
        fresh.touch()
        assert Path(result.path).stat().st_mode == fresh.stat().st_mode


class TestDirectory:
    @pytest.mark.asyncio
    async def test_the_directory_is_created_by_the_first_download_and_ignores_itself(self, tmp_path: Path) -> None:
        directory = tmp_path / "workspace" / ".agent" / "downloads"
        storage = _storage(directory)
        assert not directory.exists()

        await storage.save(_download())

        assert (directory / ".gitignore").read_text(encoding="utf-8") == "*\n"

    @pytest.mark.asyncio
    async def test_an_ignore_file_that_is_already_there_is_left_alone(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        (directory / ".gitignore").write_text("keep-me\n", encoding="utf-8")

        await _storage(directory).save(_download())

        assert (directory / ".gitignore").read_text(encoding="utf-8") == "keep-me\n"

    @pytest.mark.asyncio
    async def test_a_directory_that_cannot_be_created_refuses_the_download(self, tmp_path: Path) -> None:
        in_the_way = tmp_path / "a-file"
        in_the_way.write_text("x", encoding="utf-8")

        with pytest.raises(DownloadError, match="downloads folder cannot be created"):
            await _storage(in_the_way / "dl").save(_download())

    @pytest.mark.asyncio
    async def test_a_name_the_file_system_cannot_hold_refuses_the_download(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"

        with pytest.raises(DownloadError, match="cannot be created in the downloads folder"):
            await _storage(directory).save(_download(name="a" * 300 + ".pdf"))

        assert kept_files(directory) == []

    @pytest.mark.skipif(_RUNS_AS_ROOT, reason="root reads every directory")
    @pytest.mark.asyncio
    async def test_a_directory_that_cannot_be_read_refuses_the_download(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        directory.chmod(0o000)
        try:
            with pytest.raises(DownloadError, match="downloads folder cannot be read"):
                await _storage(directory).save(_download())
        finally:
            directory.chmod(0o700)


class TestQuota:
    @pytest.mark.asyncio
    async def test_a_full_directory_refuses_more_files_and_names_the_way_out(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        storage = _storage(directory, max_files=2)
        await storage.save(_download(name="a.pdf"))
        await storage.save(_download(name="b.pdf"))

        with pytest.raises(DownloadError, match="folder is full") as refused:
            await storage.save(_download(name="c.pdf"))

        assert str(directory) in refused.value.reason
        assert kept_files(directory) == ["a.pdf", "b.pdf"]

    @pytest.mark.asyncio
    async def test_the_quota_counts_what_is_on_disk_whoever_put_it_there(self, tmp_path: Path) -> None:
        """Chat sessions share the directory: a count in memory would only know one of them."""
        directory = tmp_path / "dl"
        await _storage(directory, max_files=2).save(_download(name="from-another-session.pdf"))
        (directory / "dropped-by-hand.txt").write_text("x", encoding="utf-8")

        with pytest.raises(DownloadError, match="folder is full"):
            await _storage(directory, max_files=2).save(_download())

    @pytest.mark.asyncio
    async def test_the_ignore_file_is_not_a_download(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        (directory / ".gitignore").write_text("*\n", encoding="utf-8")

        result = await _storage(directory, max_files=1).save(_download())

        assert result.file_name == "report.pdf"

    @pytest.mark.asyncio
    async def test_a_directory_at_its_byte_limit_refuses_more_files(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        (directory / "big.zip").write_bytes(b"x" * _MIB)

        with pytest.raises(DownloadError, match="folder is full"):
            await _storage(directory, max_total_mb=1).save(_download())

        assert kept_files(directory) == ["big.zip"]

    @pytest.mark.asyncio
    async def test_a_file_that_takes_the_directory_over_its_byte_limit_is_not_kept(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        storage = _storage(directory, max_total_mb=1)
        await storage.save(_download(name="first.pdf", body=b"x" * (700 * 1024)))

        with pytest.raises(DownloadError, match="folder is full"):
            await storage.save(_download(name="second.pdf", body=b"x" * (700 * 1024)))

        assert kept_files(directory) == ["first.pdf"]

    @pytest.mark.asyncio
    async def test_a_file_over_the_size_limit_is_not_kept(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"

        with pytest.raises(DownloadError, match="larger than 1 MB"):
            await _storage(directory, max_file_size_mb=1).save(_download(body=b"x" * (_MIB + 1)))

        assert kept_files(directory) == []


class TestNothingIsLeftBehind:
    @pytest.mark.asyncio
    async def test_a_file_type_that_is_not_allowed_is_refused_before_anything_is_created(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"

        with pytest.raises(DownloadError, match=r'file type "\.exe" is not allowed'):
            await _storage(directory).save(_download(name="setup.exe"))

        assert not directory.exists()

    @pytest.mark.asyncio
    async def test_a_hostile_extension_is_quoted_only_in_part(self, tmp_path: Path) -> None:
        with pytest.raises(DownloadError) as refused:
            await _storage(tmp_path / "dl").save(_download(name="x." + "e" * 200))

        assert refused.value.reason == f'file type ".{"e" * 16}" is not allowed'

    @pytest.mark.asyncio
    async def test_a_save_the_browser_fails_leaves_no_file_and_keeps_its_words_for_the_log(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "dl"
        download = _download()
        download.save_as = AsyncMock(side_effect=RuntimeError("boom"))
        download.failure = AsyncMock(return_value="net::ERR_FAILED")

        with pytest.raises(DownloadError, match="the browser could not save the file") as refused:
            await _storage(directory).save(download)

        assert "boom" in refused.value.detail
        assert "net::ERR_FAILED" in refused.value.detail
        assert "boom" not in refused.value.reason
        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_save_that_does_not_finish_in_time_leaves_no_file(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        download = _download()

        async def never_finishes(_path: str) -> None:
            await asyncio.Event().wait()

        download.save_as = AsyncMock(side_effect=never_finishes)

        with pytest.raises(DownloadError, match=r"saving did not finish within 0\.05 s"):
            await _storage(directory, download_timeout_s=0.05).save(download)

        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_cancelled_save_leaves_no_file(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        download = _download()
        saving = asyncio.Event()

        async def hangs(_path: str) -> None:
            saving.set()
            await asyncio.Event().wait()

        download.save_as = AsyncMock(side_effect=hangs)
        task = asyncio.create_task(_storage(directory).save(download))
        await saving.wait()

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_a_file_that_vanishes_after_the_save_is_reported(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        download = _download()

        async def saves_then_loses_it(path: str) -> None:
            Path(path).unlink()

        download.save_as = AsyncMock(side_effect=saves_then_loses_it)

        with pytest.raises(DownloadError, match="the saved file disappeared"):
            await _storage(directory).save(download)

        assert kept_files(directory) == []
