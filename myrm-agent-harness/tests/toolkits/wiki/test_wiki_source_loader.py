"""Wiki source loading: the real text of a page or a file, or a reason it has none — never invented content."""

from __future__ import annotations

import tracemalloc
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine
from myrm_agent_harness.toolkits.web_fetch.fetchers.http_fetcher import HttpFetcher
from myrm_agent_harness.toolkits.wiki.source_loader import (
    SourceLoadError,
    fetch_url_markdown,
    looks_like_local_path,
    read_local_file,
)
from tests.support.minimal_pdf import minimal_pdf_bytes

_ENGINE = "myrm_agent_harness.toolkits.web_fetch.web_fetch_tools"
_GET_PARSER = "myrm_agent_harness.toolkits.file_parsers.get_parser"
_HEAD_ONLY_LIMIT_BYTES = 4 * 1024 * 1024


def _engine_answering(doc: MagicMock | None) -> MagicMock:
    engine = MagicMock()
    engine.crawl = AsyncMock(return_value=doc)
    return engine


@pytest.fixture
async def real_engine(tmp_path: Path) -> AsyncIterator[FetchEngine]:
    engine = FetchEngine(adaptive_router_rules_file=tmp_path / "rules.pkl")
    yield engine
    await engine.shutdown()


class TestFetchUrlMarkdown:
    async def test_returns_the_page_markdown(self) -> None:
        engine = _engine_answering(MagicMock(page_content="# YouTube Video\n\nTranscript content here"))

        with patch(_ENGINE, engine):
            result = await fetch_url_markdown("https://www.youtube.com/watch?v=abc123")

        engine.crawl.assert_awaited_once_with("https://www.youtube.com/watch?v=abc123")
        assert result == "# YouTube Video\n\nTranscript content here"

    @pytest.mark.parametrize("page_content", ["", "  \n\t "])
    async def test_blank_page_is_an_error(self, page_content: str) -> None:
        engine = _engine_answering(MagicMock(page_content=page_content))

        with patch(_ENGINE, engine), pytest.raises(SourceLoadError, match="No readable content"):
            await fetch_url_markdown("https://example.com/empty")

    async def test_missing_document_is_an_error(self) -> None:
        with patch(_ENGINE, _engine_answering(None)), pytest.raises(SourceLoadError, match=r"example\.com/blocked"):
            await fetch_url_markdown("https://example.com/blocked")

    async def test_unexpected_engine_failure_propagates(self) -> None:
        engine = MagicMock()
        engine.crawl = AsyncMock(side_effect=RuntimeError("engine unavailable"))

        with patch(_ENGINE, engine), pytest.raises(RuntimeError, match="engine unavailable"):
            await fetch_url_markdown("https://example.com/article")

    @pytest.mark.parametrize(
        "url",
        [
            "http://169.254.169.254/latest/meta-data/",
            "http://127.0.0.1:9/",
            "http://[::1]:9/",
            "http://10.0.0.1/",
        ],
    )
    async def test_private_target_is_blocked_before_any_request(self, real_engine: FetchEngine, url: str) -> None:
        """The loader has no fetch path of its own: the engine's SSRF gate is the only way to a URL."""
        with (
            patch(_ENGINE, real_engine),
            patch.object(HttpFetcher, "fetch", new_callable=AsyncMock) as http_fetch,
            pytest.raises(SourceLoadError, match="No readable content"),
        ):
            await fetch_url_markdown(url)

        http_fetch.assert_not_awaited()


class TestReadLocalFile:
    async def test_utf8_text_of_an_unsupported_extension_is_read(self, tmp_path: Path) -> None:
        path = tmp_path / "server.log"
        path.write_text("启动完成\nready", encoding="utf-8")

        assert await read_local_file(path) == "启动完成\nready"

    async def test_utf8_bom_is_dropped(self, tmp_path: Path) -> None:
        path = tmp_path / "settings.toml"
        path.write_bytes(b"\xef\xbb\xbfname = 1\n")

        assert await read_local_file(path) == "name = 1\n"

    async def test_supported_format_goes_through_its_parser(self, tmp_path: Path) -> None:
        path = tmp_path / "table.csv"
        path.write_text("a,b\n1,2\n", encoding="utf-8")

        assert await read_local_file(path) == "| a | b |\n| --- | --- |\n| 1 | 2 |"

    async def test_real_pdf_is_read_through_the_default_parser(self, tmp_path: Path) -> None:
        """Nothing is mocked: a real PDF goes through the parser registry to its text."""
        path = tmp_path / "contract.pdf"
        path.write_bytes(minimal_pdf_bytes("Wiki ingest contract terms"))

        assert "Wiki ingest contract terms" in await read_local_file(path)

    async def test_parser_that_finds_no_text_is_an_error(self, tmp_path: Path) -> None:
        path = tmp_path / "scan.pdf"
        path.write_bytes(b"%PDF-1.4")
        parser = MagicMock()
        parser.parse = AsyncMock(return_value="  \n")

        with patch(_GET_PARSER, return_value=parser), pytest.raises(SourceLoadError, match="found no text"):
            await read_local_file(path)

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("setup.exe", b"MZ\x90\x00" + bytes(range(256)) * 8),
            ("blob.dat", bytes(range(32)) * 16),
        ],
    )
    async def test_binary_file_is_refused(self, tmp_path: Path, name: str, content: bytes) -> None:
        path = tmp_path / name
        path.write_bytes(content)

        with pytest.raises(SourceLoadError, match="binary file"):
            await read_local_file(path)

    async def test_archive_is_refused(self, tmp_path: Path) -> None:
        path = tmp_path / "bundle.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a.txt", "hello")

        with pytest.raises(SourceLoadError, match="binary file"):
            await read_local_file(path)

    async def test_text_in_another_encoding_is_refused(self, tmp_path: Path) -> None:
        """Decoding GBK as UTF-8 with replacement characters would put garbage into the knowledge base."""
        path = tmp_path / "legacy.log"
        path.write_bytes("你好，世界".encode("gbk"))

        with pytest.raises(SourceLoadError, match="not valid UTF-8"):
            await read_local_file(path)

    @pytest.mark.parametrize("content", [b"", b"  \n\t\n"])
    async def test_file_without_text_is_refused(self, tmp_path: Path, content: bytes) -> None:
        path = tmp_path / "blank.log"
        path.write_bytes(content)

        with pytest.raises(SourceLoadError, match="is empty"):
            await read_local_file(path)

    async def test_directory_is_refused_whatever_its_name(self, tmp_path: Path) -> None:
        folder = tmp_path / "notes.pdf"
        folder.mkdir()

        with pytest.raises(SourceLoadError, match="not a regular file"):
            await read_local_file(folder)

    async def test_missing_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(SourceLoadError, match="not a regular file"):
            await read_local_file(tmp_path / "gone.log")

    async def test_unreadable_file_is_refused_without_operating_system_detail(self, tmp_path: Path) -> None:
        path = tmp_path / "locked.log"
        path.write_text("secret", encoding="utf-8")

        with (
            patch.object(Path, "open", side_effect=PermissionError("denied")),
            pytest.raises(SourceLoadError, match=r"locked\.log could not be read") as raised,
        ):
            await read_local_file(path)

        assert "denied" not in str(raised.value)
        assert isinstance(raised.value.__cause__, PermissionError)

    async def test_binary_verdict_reads_only_the_head_of_a_large_file(self, tmp_path: Path) -> None:
        """A 64 MiB binary file is refused from its first bytes without being loaded into memory."""
        path = tmp_path / "blob.dat"
        with path.open("wb") as handle:
            handle.truncate(64 * 1024 * 1024)

        tracemalloc.start()
        try:
            with pytest.raises(SourceLoadError, match="binary file"):
                await read_local_file(path)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert peak < _HEAD_ONLY_LIMIT_BYTES


class TestLooksLikeLocalPath:
    def test_existing_file_is_a_local_path(self, tmp_path: Path) -> None:
        path = tmp_path / "notes.md"
        path.write_text("hello", encoding="utf-8")

        assert looks_like_local_path(str(path))

    @pytest.mark.parametrize("source", ["https://example.com/a", "http://example.com/a"])
    def test_url_is_not_a_local_path(self, source: str) -> None:
        assert not looks_like_local_path(source)

    @pytest.mark.parametrize("source", ["", "   "])
    def test_blank_string_is_not_a_local_path(self, source: str) -> None:
        """Path("") is the current directory, which exists, but it is not something to ingest."""
        assert not looks_like_local_path(source)

    def test_missing_file_is_not_a_local_path(self, tmp_path: Path) -> None:
        assert not looks_like_local_path(str(tmp_path / "missing.md"))

    def test_pasted_text_is_not_a_local_path(self) -> None:
        assert not looks_like_local_path("a line of pasted text\nand another one")

    def test_overlong_string_is_not_a_local_path(self, tmp_path: Path) -> None:
        assert not looks_like_local_path(str(tmp_path / ("x" * 300)))
