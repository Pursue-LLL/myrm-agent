"""Binary content detection and routing.

When HttpFetcher receives a non-text response (PDF, image, Office documents),
this module detects the content type via a three-layer strategy and routes
the raw bytes to the appropriate file parser for extraction.

[INPUT]
- toolkits.file_parsers (POS: File parsers toolkit entry point.)
- utils.content_sniff::magic_extension (POS: Format signature to file extension)

[OUTPUT]
- MAX_BINARY_SIZE: the largest file body the router parses; a larger one is dropped
- route_binary_content: Detect and parse binary content from a FetchResult

[POS]
Binary content detection and routing for non-HTML URLs (PDF, images, documents).
Three-layer detection: Content-Type → Content-Disposition → Magic Bytes.
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from langchain_core.documents import Document

from myrm_agent_harness.utils.content_sniff import magic_extension

logger = logging.getLogger(__name__)

MAX_BINARY_SIZE = 20 * 1024 * 1024  # 20 MB safety limit

_CONTENT_TYPE_MAP: dict[str, str] = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    "application/msword": ".doc",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.ms-powerpoint": ".ppt",
    "image/png": ".png",
    "image/jpeg": ".jpeg",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
}

_CD_FILENAME_RE = re.compile(r"filename\*?=(?:UTF-8''|utf-8'')?[\"']?([^\"';\s]+)", re.IGNORECASE)


def _detect_extension_from_content_type(content_type: str) -> str | None:
    """Layer 1: Map Content-Type header to file extension."""
    ct = content_type.split(";")[0].strip().lower()
    return _CONTENT_TYPE_MAP.get(ct)


def _detect_extension_from_disposition(headers: dict[str, str]) -> str | None:
    """Layer 2: Extract filename from Content-Disposition header."""
    cd = headers.get("content-disposition") or headers.get("Content-Disposition") or ""
    match = _CD_FILENAME_RE.search(cd)
    if not match:
        return None
    filename = match.group(1).strip("\"'")
    ext = Path(filename).suffix.lower()
    return ext if ext else None


def detect_binary_extension(headers: dict[str, str], data: bytes) -> str | None:
    """Three-layer detection: CT → CD → Magic. Returns extension or None."""
    ct = headers.get("content-type") or headers.get("Content-Type") or ""
    ext = _detect_extension_from_content_type(ct)
    if ext:
        return ext

    ext = _detect_extension_from_disposition(headers)
    if ext:
        return ext

    return magic_extension(data)


async def route_binary_content(
    raw_body: bytes,
    headers: dict[str, str],
    url: str,
) -> Document | None:
    """Route binary content to appropriate parser and return a Document.

    Returns None if the content type is unrecognized, no parser supports it, or parsing fails.
    """
    if len(raw_body) > MAX_BINARY_SIZE:
        logger.warning("Binary content too large (%d bytes), skipping: %s", len(raw_body), url[:100])
        return None

    ext = detect_binary_extension(headers, raw_body)
    if not ext:
        logger.info("Unrecognized binary format for %s, skipping", url[:100])
        return None

    from myrm_agent_harness.toolkits.file_parsers import is_supported

    if not is_supported(f"file{ext}"):
        logger.info("No parser available for extension %s: %s", ext, url[:100])
        return None

    tmp_file = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)  # noqa: SIM115  manual lifecycle: reused by path after close, removed in finally
        tmp_file.write(raw_body)
        tmp_file.flush()
        tmp_file.close()

        from myrm_agent_harness.toolkits.file_parsers import get_parser

        parser = get_parser(tmp_file.name)
        result = await parser.parse(tmp_file.name)

        if not result or not result.strip():
            return None

        return Document(
            page_content=result[:100_000],
            metadata={
                "url": url,
                "source_type": f"binary_{ext.lstrip('.')}",
                "extension": ext,
            },
        )
    except Exception as e:
        logger.warning("Failed to parse binary content from %s: %s", url[:100], e)
        return None
    finally:
        if tmp_file:
            Path(tmp_file.name).unlink(missing_ok=True)
