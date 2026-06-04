"""File content extraction for service-layer callers (bytes in, text out).

[INPUT]
myrm_agent_harness.toolkits.file_parsers (POS: PDF/Office 解析)

[OUTPUT]
extract_pdf_text_from_bytes / extract_document_text_from_bytes

[POS]
服务层文件文本提取，供 Kanban 附件等非 HTTP 路径调用。
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from myrm_agent_harness.toolkits.file_parsers.pdf_content_extractor import (
    PDFExtractConfig,
    extract_pdf_content,
)

logger = logging.getLogger(__name__)

_OFFICE_SUFFIXES = frozenset({".docx", ".xlsx", ".xls", ".pptx", ".ppt"})


async def extract_pdf_text_from_bytes(content: bytes) -> str:
    """Extract plain text from PDF bytes via harness pdf_content_extractor."""
    if not content:
        return ""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    path = Path(tmp.name)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        result = await extract_pdf_content(str(path), PDFExtractConfig())
        return result.text or ""
    except Exception:
        logger.warning("PDF text extraction failed", exc_info=True)
        return ""
    finally:
        path.unlink(missing_ok=True)


async def extract_document_text_from_bytes(content: bytes, *, filename: str) -> str:
    """Extract Markdown text from Office document bytes."""
    if not content:
        return ""
    ext = Path(filename).suffix.lower()
    if ext not in _OFFICE_SUFFIXES:
        logger.warning("Unsupported document extension for extraction: %s", ext)
        return ""

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    path = Path(tmp.name)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return await _parse_document(path, ext)
    except Exception:
        logger.warning("Document text extraction failed for %s", filename, exc_info=True)
        return ""
    finally:
        path.unlink(missing_ok=True)


async def _parse_document(file_path: Path, ext: str) -> str:
    if ext == ".docx":
        from myrm_agent_harness.toolkits.file_parsers.docx import DocxParser

        parser = DocxParser()
    elif ext in (".xlsx", ".xls"):
        from myrm_agent_harness.toolkits.file_parsers.excel import ExcelParser

        parser = ExcelParser()
    elif ext in (".pptx", ".ppt"):
        from myrm_agent_harness.toolkits.file_parsers.pptx import PptxParser

        parser = PptxParser()
    else:
        return ""
    return await parser.parse(str(file_path))
