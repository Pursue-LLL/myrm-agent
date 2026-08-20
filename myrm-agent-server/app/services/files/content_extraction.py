"""File content extraction for service-layer callers (bytes in, text out).

[INPUT]
myrm_agent_harness.toolkits.file_parsers (POS: PDF/Office/Notebook 解析)

[OUTPUT]
extract_pdf_text_from_bytes / extract_pdf_from_path / extract_document_text_from_bytes / extract_document_from_path

[POS]
服务层文件内容提取，供 Kanban 附件与 api/files 提取端点共用。
支持格式：.docx, .xlsx, .xls, .pptx, .ppt, .ipynb
"""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.toolkits.file_parsers.pdf.pdf_content_extractor import (
    PDFExtractConfig,
    PDFExtractResult,
    extract_pdf_content,
)

logger = logging.getLogger(__name__)

SUPPORTED_DOCUMENT_EXTENSIONS = frozenset({".docx", ".xlsx", ".xls", ".pptx", ".ppt", ".ipynb"})


@dataclass(frozen=True, slots=True)
class DocumentImageItem:
    data: bytes
    mime_type: str
    embed_id: str = ""


@dataclass(frozen=True, slots=True)
class DocumentExtractResult:
    text: str
    format: str
    images: tuple[DocumentImageItem, ...] = field(default_factory=tuple)


async def extract_pdf_from_path(
    file_path: Path,
    config: PDFExtractConfig | None = None,
) -> PDFExtractResult:
    """Extract PDF content from a filesystem path (full harness result)."""
    cfg = config or PDFExtractConfig()
    return await extract_pdf_content(str(file_path), cfg)


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
    """Extract Markdown text from document bytes (.docx/.xlsx/.xls/.pptx/.ppt/.ipynb)."""
    result = await extract_document_from_bytes(content, filename=filename)
    return result.text


async def extract_document_from_bytes(content: bytes, *, filename: str) -> DocumentExtractResult:
    """Extract Markdown text and embedded image bytes from supported documents."""
    if not content:
        return DocumentExtractResult(text="", format="")
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_DOCUMENT_EXTENSIONS:
        logger.warning("Unsupported document extension for extraction: %s", ext)
        return DocumentExtractResult(text="", format=ext.lstrip("."))

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    path = Path(tmp.name)
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return await _parse_document_with_assets(path, ext)
    except Exception:
        logger.warning("Document extraction failed for %s", filename, exc_info=True)
        return DocumentExtractResult(text="", format=ext.lstrip("."))
    finally:
        path.unlink(missing_ok=True)


async def extract_document_from_path(file_path: Path, ext: str) -> DocumentExtractResult:
    """Extract Markdown text and embedded assets from a document on disk."""
    return await _parse_document_with_assets(file_path, ext.lower())


async def _parse_document_with_assets(file_path: Path, ext: str) -> DocumentExtractResult:
    text = await _parse_document(file_path, ext)
    images: tuple[DocumentImageItem, ...] = ()
    if ext == ".docx":
        from myrm_agent_harness.toolkits.file_parsers.docx import DocxParser
        from myrm_agent_harness.toolkits.file_parsers.gfm_normalize import (
            normalize_to_gfm_markdown,
        )

        parser = DocxParser()
        text = normalize_to_gfm_markdown(text)
        embedded = parser.embedded_images(str(file_path))
        if embedded:
            images = tuple(
                DocumentImageItem(data=img.data, mime_type=img.mime_type, embed_id=img.embed_id) for img in embedded.values()
            )
    return DocumentExtractResult(text=text, format=ext.lstrip("."), images=images)


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
    elif ext == ".ipynb":
        from myrm_agent_harness.toolkits.file_parsers.ipynb import IpynbParser

        parser = IpynbParser()
    else:
        return ""
    return await parser.parse(str(file_path))
