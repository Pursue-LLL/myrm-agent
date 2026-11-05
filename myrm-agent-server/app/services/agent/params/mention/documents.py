"""[INPUT]
- myrm_agent_harness.toolkits.file_parsers (POS: Office/PDF document parsers)

[OUTPUT]
- _parse_document / _parse_stored_document: Office text extraction from a path or from bytes
- _DOCUMENT_EXTENSIONS / _BINARY_EXTENSIONS: the classification both import paths share

[POS]
Document classification and parsing for @-mentioned files. Kept separate because both the workspace
file path and the stored-upload path need the same extension sets and the same parsers.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_DOCUMENT_EXTENSIONS = {".docx", ".xlsx", ".xls", ".pptx", ".ppt"}
_BINARY_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".bmp",
    ".ico",
    ".mp3",
    ".mp4",
    ".avi",
    ".mov",
    ".zip",
    ".tar",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".pdf",
}


def _parse_document(path: str, ext: str) -> str | None:
    """Parse Office document to text using Harness parsers (sync)."""
    try:
        if ext == ".docx":
            from myrm_agent_harness.toolkits.file_parsers import DocxParser

            return DocxParser()._parse_sync(path)
        if ext in (".xlsx", ".xls"):
            from myrm_agent_harness.toolkits.file_parsers import ExcelParser

            return ExcelParser()._parse_sync(path)
        if ext in (".pptx", ".ppt"):
            from myrm_agent_harness.toolkits.file_parsers import PptxParser

            return PptxParser()._parse_sync(path)
    except Exception as e:
        logger.warning("Failed to parse document %s: %s", path, e)
    return None


async def _parse_stored_document(content: bytes, ext: str, filename: str) -> str | None:
    suffix = ext if ext else Path(filename).suffix.lower()
    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            temp.write(content)
            temp_path = temp.name
        if suffix == ".pdf":
            from myrm_agent_harness.toolkits.file_parsers import SmartPDFParser

            return await SmartPDFParser().parse(temp_path)
        return _parse_document(temp_path, suffix)
    except Exception as exc:
        logger.warning("Failed to parse stored document %s: %s", filename, exc)
        return None
    finally:
        if temp_path:
            try:
                os.unlink(temp_path)
            except OSError:
                pass
