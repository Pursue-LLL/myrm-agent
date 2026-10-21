"""Integration tests for services/files/content_extraction (non-mocked parsers)."""

from __future__ import annotations

import pytest

from app.services.files.content_extraction import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    extract_document_text_from_bytes,
    extract_pdf_text_from_bytes,
)

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 200 200]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n0\n%%EOF\n"
)


@pytest.mark.asyncio
async def test_extract_pdf_text_from_bytes_empty() -> None:
    assert await extract_pdf_text_from_bytes(b"") == ""


@pytest.mark.asyncio
async def test_extract_pdf_text_from_minimal_pdf() -> None:
    text = await extract_pdf_text_from_bytes(_MINIMAL_PDF)
    assert isinstance(text, str)


@pytest.mark.asyncio
async def test_extract_document_unsupported_extension() -> None:
    text = await extract_document_text_from_bytes(b"data", filename="notes.bin")
    assert text == ""


@pytest.mark.asyncio
async def test_extract_document_empty_ipynb() -> None:
    assert await extract_document_text_from_bytes(b"", filename="notebook.ipynb") == ""


@pytest.mark.asyncio
async def test_extract_document_minimal_ipynb() -> None:
    minimal_ipynb = b'{"cells":[{"cell_type":"code","source":["print(1)"],"metadata":{},"outputs":[]}],"metadata":{},"nbformat":4,"nbformat_minor":0}'
    text = await extract_document_text_from_bytes(minimal_ipynb, filename="test.ipynb")
    assert isinstance(text, str)
    assert "print(1)" in text


def test_supported_document_extensions_stable() -> None:
    assert ".docx" in SUPPORTED_DOCUMENT_EXTENSIONS
    assert ".ipynb" in SUPPORTED_DOCUMENT_EXTENSIONS
    assert ".bin" not in SUPPORTED_DOCUMENT_EXTENSIONS
