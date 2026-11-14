"""Attachment text extraction with the real parsers (no mocked extract methods)."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.kanban.task_runner import KanbanTaskRunner


def _minimal_pdf_bytes() -> bytes:
    """PDF with Helvetica + literal text (valid xref offsets for pdfplumber)."""
    return b"""%PDF-1.4
1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj
2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj
3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj
4 0 obj<< /Length 44 >>stream
BT /F1 24 Tf 100 700 Td (kanban pdf text) Tj ET
endstream
endobj
5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000264 00000 n 
0000000360 00000 n 
trailer<< /Size 6 /Root 1 0 R >>
startxref
433
%%EOF"""


class TestBuildMultimodalRealExtraction:
    """Integration tests using real parsers (no mocked extract methods)."""

    @pytest.mark.asyncio
    async def test_real_pdf_extraction_in_query(self) -> None:
        pytest.importorskip("pdfplumber")
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")
        pdf_bytes = _minimal_pdf_bytes()

        mock_file = MagicMock()
        mock_file.content_type = "application/pdf"
        mock_file.filename = "report.pdf"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_content = AsyncMock(return_value=pdf_bytes)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, str)
        assert "kanban pdf text" in result
        assert "report.pdf" in result
        assert "## Attachment:" in result

    @pytest.mark.asyncio
    async def test_real_docx_extraction_in_query(self, tmp_path: Path) -> None:
        docx = pytest.importorskip("docx")
        Document = docx.Document

        docx_path = tmp_path / "spec.docx"
        doc = Document()
        doc.add_paragraph("kanban fixture paragraph")
        doc.save(str(docx_path))
        docx_bytes = docx_path.read_bytes()

        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock()
        mock_file.content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        mock_file.filename = "spec.docx"

        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_content = AsyncMock(return_value=docx_bytes)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, str)
        assert "kanban fixture paragraph" in result
        assert "spec.docx" in result

    @pytest.mark.asyncio
    async def test_extract_enabled_empty_pdf_falls_back_to_reference(self) -> None:
        from tests.services.files.test_content_extraction import _MINIMAL_PDF

        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock(content_type="application/pdf", filename="empty.pdf")
        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_content = AsyncMock(return_value=_MINIMAL_PDF)

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": True}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, str)
        assert "[Attachment: empty.pdf]" in result
        assert "## Attachment:" not in result

    @pytest.mark.asyncio
    async def test_extract_disabled_pdf_reference_only(self) -> None:
        runner = KanbanTaskRunner(AsyncMock())
        task = KanbanTask(task_id="t1", board_id="b1", title="T")

        mock_file = MagicMock(content_type="application/pdf", filename="report.pdf")
        mock_fs = MagicMock()
        mock_fs.get_file = AsyncMock(return_value=mock_file)
        mock_fs.get_content = AsyncMock(return_value=_minimal_pdf_bytes())

        mock_configs = MagicMock()
        mock_configs.personal_settings_dict = {"extractDocumentText": False}

        with (
            patch.object(runner, "_load_attachment_ids", return_value=["f1"]),
            patch("app.core.storage.files_service", mock_fs),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=mock_configs,
            ),
        ):
            result = await runner._build_multimodal_query(task, "ctx")

        assert isinstance(result, str)
        assert "[Attachment: report.pdf]" in result
        assert "## Attachment:" not in result
