"""DownloadStorage: a unique name per download, the directory it is created in, and the quota it keeps."""

from __future__ import annotations

import asyncio
import errno
import os
from pathlib import Path
from typing import NoReturn
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.core.security.path import ConfinedDirectory
from myrm_agent_harness.toolkits.browser.session.download import storage as storage_module
from myrm_agent_harness.toolkits.browser.session.download.errors import DownloadError
from myrm_agent_harness.toolkits.browser.session.download.storage import sanitize_filename
from tests.toolkits.browser._download_doubles import (
    REPORT_URL,
    download_named,
    finished_file,
    kept_files,
    storage_in,
)

_MIB = 1024 * 1024
_RUNS_AS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0


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

    @pytest.mark.parametrize("stem", ["a" * 300, "文" * 100, "e\u0301" * 150], ids=["ascii", "three-byte", "combining"])
    def test_a_long_name_is_cut_to_the_byte_limit_at_a_character_boundary_and_keeps_its_extension(
        self, stem: str
    ) -> None:
        name = sanitize_filename(f"{stem}.pdf")

        assert len(name.encode()) <= 200
        assert name.endswith(".pdf")
        assert name.removesuffix(".pdf") and stem.startswith(name.removesuffix(".pdf"))

    def test_a_name_within_the_limit_is_untouched(self) -> None:
        assert sanitize_filename("文" * 60 + ".pdf") == "文" * 60 + ".pdf"

    def test_a_long_tail_after_a_dot_is_part_of_the_name_and_not_a_type(self) -> None:
        name = sanitize_filename("report." + "e" * 300)

        assert len(name.encode()) <= 200
        assert name.startswith("report.eeee")


class TestNames:
    @pytest.mark.asyncio
    async def test_the_result_says_where_the_file_is_and_what_it_holds(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"

        result = await storage_in(directory).save(download_named(body=b"twelve bytes"))

        assert result.url == REPORT_URL
        assert result.path == str(directory / "report.pdf")
        assert (result.file_name, result.file_size, result.file_type) == ("report.pdf", 12, "pdf")
        assert (directory / "report.pdf").read_bytes() == b"twelve bytes"

    @pytest.mark.asyncio
    async def test_downloads_with_one_name_are_saved_under_distinct_names(self, tmp_path: Path) -> None:
        storage = storage_in(tmp_path / "dl")

        names = [(await storage.save(download_named())).file_name for _ in range(3)]

        assert names == ["report.pdf", "report (1).pdf", "report (2).pdf"]

    @pytest.mark.asyncio
    async def test_downloads_finishing_at_the_same_moment_each_get_their_own_file(self, tmp_path: Path) -> None:
        storage = storage_in(tmp_path / "dl")
        count = 5
        waiting = 0
        all_finished = asyncio.Event()

        def finishing_together(index: int) -> MagicMock:
            download = download_named()

            async def path() -> Path:
                nonlocal waiting
                waiting += 1
                if waiting == count:
                    all_finished.set()
                await all_finished.wait()
                return finished_file(f"body-{index}".encode())

            download.path = AsyncMock(side_effect=path)
            return download

        results = await asyncio.gather(*(storage.save(finishing_together(i)) for i in range(count)))

        assert len({result.file_name for result in results}) == count
        for index, result in enumerate(results):
            assert Path(result.path).read_bytes() == f"body-{index}".encode()

    @pytest.mark.asyncio
    async def test_a_file_without_extension_is_kept_without_a_type(self, tmp_path: Path) -> None:
        result = await storage_in(tmp_path / "dl").save(download_named(name="README"))

        assert (result.file_name, result.file_type) == ("README", None)

    @pytest.mark.asyncio
    async def test_a_saved_file_has_the_mode_of_a_new_file(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        result = await storage_in(directory).save(download_named())

        fresh = directory / "fresh"
        fresh.touch()
        assert Path(result.path).stat().st_mode == fresh.stat().st_mode

    @pytest.mark.asyncio
    async def test_a_name_over_the_limit_is_kept_cut_and_a_taken_one_still_gets_its_number(
        self, tmp_path: Path
    ) -> None:
        storage = storage_in(tmp_path / "dl")

        first = await storage.save(download_named(name="a" * 300 + ".pdf"))
        second = await storage.save(download_named(name="a" * 300 + ".pdf"))

        assert first.file_name.endswith(".pdf") and len(first.file_name.encode()) <= 200
        assert second.file_name == first.file_name.removesuffix(".pdf") + " (1).pdf"
        assert len(second.file_name.encode()) <= 255

    @pytest.mark.asyncio
    async def test_a_file_larger_than_one_chunk_is_copied_whole(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(storage_module, "_COPY_CHUNK_BYTES", 1000)
        body = bytes(range(256)) * 20

        result = await storage_in(tmp_path / "dl").save(download_named(body=body))

        assert Path(result.path).read_bytes() == body
        assert result.file_size == len(body)


class TestDirectory:
    @pytest.mark.asyncio
    async def test_the_directory_is_created_by_the_first_download_and_ignores_itself(self, tmp_path: Path) -> None:
        directory = tmp_path / "workspace" / ".agent" / "downloads"
        storage = storage_in(directory, root=tmp_path)
        assert not directory.exists()

        await storage.save(download_named())

        assert (directory / ".gitignore").read_text(encoding="utf-8") == "*\n"

    @pytest.mark.asyncio
    async def test_an_ignore_file_that_is_already_there_is_left_alone(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        (directory / ".gitignore").write_text("keep-me\n", encoding="utf-8")

        await storage_in(directory).save(download_named())

        assert (directory / ".gitignore").read_text(encoding="utf-8") == "keep-me\n"

    @pytest.mark.asyncio
    async def test_a_directory_that_cannot_be_opened_refuses_the_download(self, tmp_path: Path) -> None:
        in_the_way = tmp_path / "a-file"
        in_the_way.write_text("x", encoding="utf-8")

        with pytest.raises(DownloadError, match="downloads folder cannot be opened"):
            await storage_in(in_the_way / "dl", root=tmp_path).save(download_named())

    @pytest.mark.skipif(_RUNS_AS_ROOT, reason="root opens every directory")
    @pytest.mark.asyncio
    async def test_a_directory_without_permission_refuses_the_download(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        directory.chmod(0o000)
        try:
            with pytest.raises(DownloadError, match="downloads folder cannot be opened"):
                await storage_in(directory).save(download_named())
        finally:
            directory.chmod(0o700)

    @pytest.mark.asyncio
    async def test_a_directory_that_cannot_be_listed_refuses_the_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def unreadable(_self: ConfinedDirectory) -> NoReturn:
            raise OSError(errno.EIO, "Input/output error")

        monkeypatch.setattr(ConfinedDirectory, "scandir", unreadable)

        with pytest.raises(DownloadError, match="downloads folder cannot be read") as refused:
            await storage_in(tmp_path / "dl").save(download_named())

        assert "Input/output error" in refused.value.detail

    @pytest.mark.asyncio
    async def test_a_file_the_file_system_cannot_create_refuses_the_download(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        create_new = ConfinedDirectory.create_new

        def refuses_downloads(self: ConfinedDirectory, name: str) -> int:
            if name == ".gitignore":
                return create_new(self, name)
            raise OSError(errno.ENOSPC, "No space left on device")

        monkeypatch.setattr(ConfinedDirectory, "create_new", refuses_downloads)
        directory = tmp_path / "dl"

        with pytest.raises(DownloadError, match="cannot be created in the downloads folder"):
            await storage_in(directory).save(download_named())

        assert kept_files(directory) == []


class TestQuota:
    @pytest.mark.asyncio
    async def test_a_full_directory_refuses_more_files_and_names_the_way_out(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        storage = storage_in(directory, max_files=2)
        await storage.save(download_named(name="a.pdf"))
        await storage.save(download_named(name="b.pdf"))
        late = download_named(name="c.pdf")

        with pytest.raises(DownloadError, match="folder is full") as refused:
            await storage.save(late)

        assert str(directory) in refused.value.reason
        assert kept_files(directory) == ["a.pdf", "b.pdf"]
        late.path.assert_not_awaited()  # a full folder refuses before the body is waited for

    @pytest.mark.asyncio
    async def test_the_quota_counts_what_is_on_disk_whoever_put_it_there(self, tmp_path: Path) -> None:
        """Chat sessions share the directory: a count in memory would only know one of them."""
        directory = tmp_path / "dl"
        await storage_in(directory, max_files=2).save(download_named(name="from-another-session.pdf"))
        (directory / "dropped-by-hand.txt").write_text("x", encoding="utf-8")

        with pytest.raises(DownloadError, match="folder is full"):
            await storage_in(directory, max_files=2).save(download_named())

    @pytest.mark.asyncio
    async def test_the_ignore_file_is_not_a_download(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        (directory / ".gitignore").write_text("*\n", encoding="utf-8")

        result = await storage_in(directory, max_files=1).save(download_named())

        assert result.file_name == "report.pdf"

    @pytest.mark.asyncio
    async def test_a_directory_at_its_byte_limit_refuses_more_files_before_the_body_is_waited_for(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "dl"
        directory.mkdir()
        (directory / "big.zip").write_bytes(b"x" * _MIB)
        late = download_named()

        with pytest.raises(DownloadError, match="folder is full"):
            await storage_in(directory, max_total_mb=1).save(late)

        assert kept_files(directory) == ["big.zip"]
        late.path.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_file_that_would_take_the_directory_over_its_byte_limit_is_refused_before_it_is_copied(
        self, tmp_path: Path
    ) -> None:
        directory = tmp_path / "dl"
        storage = storage_in(directory, max_total_mb=1)
        await storage.save(download_named(name="first.pdf", body=b"x" * (700 * 1024)))

        with pytest.raises(DownloadError, match="folder is full"):
            await storage.save(download_named(name="second.pdf", body=b"x" * (700 * 1024)))

        assert kept_files(directory) == ["first.pdf"]

    @pytest.mark.asyncio
    async def test_a_file_over_the_size_limit_is_not_kept(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"

        with pytest.raises(DownloadError, match="larger than 1 MB"):
            await storage_in(directory, max_file_size_mb=1).save(download_named(body=b"x" * (_MIB + 1)))

        assert kept_files(directory) == []

    @pytest.mark.asyncio
    async def test_an_empty_file_is_refused_and_not_kept(self, tmp_path: Path) -> None:
        directory = tmp_path / "dl"

        with pytest.raises(DownloadError, match="the downloaded file is empty"):
            await storage_in(directory).save(download_named(body=b""))

        assert kept_files(directory) == []
