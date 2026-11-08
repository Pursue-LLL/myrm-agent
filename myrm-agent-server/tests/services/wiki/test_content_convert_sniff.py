"""Tests for wiki source_sync content sniff conversion."""

from __future__ import annotations

import logging
import zipfile

import pytest

from app.services.wiki.source_sync.content_convert import bytes_to_wiki_markdown

_NOTES = (
    "知识库编译流程会先读取原始资料，再由模型提炼要点并写入对应的页面。\n"
    "如果资料的编码无法确认，系统宁可明确拒绝，也不会把乱码写进知识库。\n"
)
_STAFF_CSV = "姓名,部门,城市,备注\n张三,研发部,上海,负责检索服务的维护\n李四,产品部,北京,负责知识库的需求整理\n"


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_sniffs_mislabeled_csv() -> None:
    content = b"name,score\nalice,1\nbob,2\n"
    text = await bytes_to_wiki_markdown(content, filename="upload.bin", mime_type="application/octet-stream")
    assert text is not None
    assert "| name | score |" in text


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_sniffs_rtf() -> None:
    content = b"{\\rtf1\\ansi Hello from RTF}"
    text = await bytes_to_wiki_markdown(content, filename="note.txt", mime_type="text/plain")
    assert text is not None
    assert "Hello" in text


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_sniffs_epub_zip() -> None:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("chapter.xhtml", "<html><body><p>EPUB chapter</p></body></html>")
    text = await bytes_to_wiki_markdown(buffer.getvalue(), filename="book.dat", mime_type="application/octet-stream")
    assert text is not None
    assert "EPUB chapter" in text


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_reads_gbk_text() -> None:
    text = await bytes_to_wiki_markdown(_NOTES.encode("gbk"), filename="notes.txt", mime_type="text/plain")

    assert text == _NOTES.strip()


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_reads_gbk_csv() -> None:
    text = await bytes_to_wiki_markdown(_STAFF_CSV.encode("gbk"), filename="staff.csv", mime_type="text/csv")

    assert text is not None
    assert text.splitlines()[0] == "| 姓名 | 部门 | 城市 | 备注 |"
    assert "| 李四 | 产品部 | 北京 | 负责知识库的需求整理 |" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filename", "mime_type", "content"),
    [
        ("short.txt", "text/plain", "你好，世界".encode("gbk")),
        ("short.csv", "text/csv", "你好,世界\n".encode("gbk")),
    ],
)
async def test_bytes_to_wiki_markdown_skips_text_in_an_unidentifiable_encoding(
    caplog: pytest.LogCaptureFixture, filename: str, mime_type: str, content: bytes
) -> None:
    """Replacement-character garbage must not become a wiki source: the file is skipped with a warning."""
    with caplog.at_level(logging.WARNING):
        text = await bytes_to_wiki_markdown(content, filename=filename, mime_type=mime_type)

    assert text is None
    assert f"Skipped {filename}" in caplog.text
