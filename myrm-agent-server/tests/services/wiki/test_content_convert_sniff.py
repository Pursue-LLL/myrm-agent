"""Tests for wiki source_sync content sniff conversion."""

from __future__ import annotations

import zipfile

import pytest

from app.services.wiki.source_sync.content_convert import bytes_to_wiki_markdown


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_sniffs_mislabeled_csv() -> None:
    content = b"name,score\nalice,1\nbob,2\n"
    text = await bytes_to_wiki_markdown(
        content, filename="upload.bin", mime_type="application/octet-stream"
    )
    assert text is not None
    assert "| name | score |" in text


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_sniffs_rtf() -> None:
    content = b"{\\rtf1\\ansi Hello from RTF}"
    text = await bytes_to_wiki_markdown(
        content, filename="note.txt", mime_type="text/plain"
    )
    assert text is not None
    assert "Hello" in text


@pytest.mark.asyncio
async def test_bytes_to_wiki_markdown_sniffs_epub_zip() -> None:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "chapter.xhtml", "<html><body><p>EPUB chapter</p></body></html>"
        )
    text = await bytes_to_wiki_markdown(
        buffer.getvalue(), filename="book.dat", mime_type="application/octet-stream"
    )
    assert text is not None
    assert "EPUB chapter" in text
