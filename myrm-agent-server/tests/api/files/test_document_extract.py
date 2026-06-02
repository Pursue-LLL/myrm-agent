"""Tests for document_extract module

Tests _validate_extension, _parse_document (sync helpers that don't
require FastAPI or DB), covering .docx, .xlsx, .xls, .pptx, .ppt.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.api.files.document_extract import _parse_document, _validate_extension
from app.core.utils.errors import StandardHTTPException


class TestValidateExtension:
    """Tests for _validate_extension."""

    def test_docx(self) -> None:
        assert _validate_extension("report.docx") == ".docx"

    def test_xlsx(self) -> None:
        assert _validate_extension("data.xlsx") == ".xlsx"

    def test_xls(self) -> None:
        assert _validate_extension("legacy.xls") == ".xls"

    def test_pptx(self) -> None:
        assert _validate_extension("slides.pptx") == ".pptx"

    def test_ppt(self) -> None:
        assert _validate_extension("old.ppt") == ".ppt"

    def test_unsupported_raises(self) -> None:
        with pytest.raises(StandardHTTPException):
            _validate_extension("image.png")

    def test_pdf_not_supported(self) -> None:
        with pytest.raises(StandardHTTPException):
            _validate_extension("doc.pdf")


class TestParseDocument:
    """Tests for _parse_document with real files."""

    @pytest.mark.asyncio
    async def test_parse_docx(self) -> None:
        from docx import Document

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            doc = Document()
            doc.add_paragraph("Extract test content")
            doc.save(f.name)
            tmp = f.name

        try:
            result = await _parse_document(Path(tmp), ".docx")
            assert "Extract test content" in result
        finally:
            os.unlink(tmp)

    @pytest.mark.asyncio
    async def test_parse_xlsx(self) -> None:
        from openpyxl import Workbook

        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
            wb = Workbook()
            ws = wb.active
            assert ws is not None
            ws.append(["Name", "Value"])
            ws.append(["Test", 42])
            wb.save(f.name)
            tmp = f.name

        try:
            result = await _parse_document(Path(tmp), ".xlsx")
            assert "Name" in result
            assert "Test" in result
        finally:
            os.unlink(tmp)

    @pytest.mark.asyncio
    async def test_parse_pptx(self) -> None:
        from pptx import Presentation

        with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
            prs = Presentation()
            slide = prs.slides.add_slide(prs.slide_layouts[0])
            slide.shapes.title.text = "Extraction Test"
            slide.placeholders[1].text = "API endpoint works"
            prs.save(f.name)
            tmp = f.name

        try:
            result = await _parse_document(Path(tmp), ".pptx")
            assert "Extraction Test" in result
            assert "API endpoint works" in result
        finally:
            os.unlink(tmp)

    @pytest.mark.asyncio
    async def test_unsupported_extension_raises(self) -> None:
        with pytest.raises(StandardHTTPException):
            await _parse_document(Path("/tmp/fake.odt"), ".odt")
