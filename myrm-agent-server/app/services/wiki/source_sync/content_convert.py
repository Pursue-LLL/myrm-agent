"""Convert cloud file bytes into wiki-ready Markdown text."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from app.services.files.content_extraction import (
    extract_document_text_from_bytes,
    extract_pdf_text_from_bytes,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.wiki import WikiStructure

_TEXT_EXTENSIONS = (".md", ".txt", ".markdown", ".csv", ".rtf")
_DOCX_EXTENSIONS = (".docx",)
_PDF_EXTENSIONS = (".pdf",)
_CONTAINER_EXTENSIONS = (".epub", ".odt", ".ods", ".odp")


async def bytes_to_wiki_markdown(
    content: bytes,
    *,
    filename: str,
    mime_type: str,
    structure: WikiStructure | None = None,
    raw_relative: str | None = None,
) -> str | None:
    if not content:
        return None
    lowered_name = filename.lower()
    lowered_mime = mime_type.lower()

    from myrm_agent_harness.toolkits.file_parsers.content_format_sniff import (
        sniff_content_format_from_bytes,
    )

    sniffed_ext = sniff_content_format_from_bytes(content)
    effective_name = filename
    if sniffed_ext and not lowered_name.endswith(sniffed_ext):
        stem = Path(filename).stem or "upload"
        effective_name = f"{stem}{sniffed_ext}"
        lowered_name = effective_name.lower()

    if lowered_mime in {"text/markdown", "text/plain"} or lowered_name.endswith(
        _TEXT_EXTENSIONS
    ):
        if lowered_name.endswith(".csv") or sniffed_ext == ".csv":
            return await _parse_with_tempfile(content, effective_name)
        if lowered_name.endswith(".rtf") or sniffed_ext == ".rtf":
            return await _parse_with_tempfile(content, effective_name)
        text = content.decode("utf-8", errors="replace").strip()
        return text or None

    if "wordprocessingml.document" in lowered_mime or lowered_name.endswith(
        _DOCX_EXTENSIONS
    ):
        return await _parse_docx_bytes(
            content,
            effective_name,
            structure=structure,
            raw_relative=raw_relative,
        )

    if lowered_mime == "application/pdf" or lowered_name.endswith(_PDF_EXTENSIONS):
        text = (await extract_pdf_text_from_bytes(content)).strip()
        return text or None

    if lowered_name.endswith(_CONTAINER_EXTENSIONS):
        return await _parse_with_tempfile(content, effective_name)

    if sniffed_ext:
        return await _parse_with_tempfile(content, effective_name)

    return None


async def _parse_docx_bytes(
    content: bytes,
    filename: str,
    *,
    structure: WikiStructure | None,
    raw_relative: str | None,
) -> str | None:
    suffix = Path(filename).suffix or ".docx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from myrm_agent_harness.toolkits.file_parsers.docx import DocxParser
        from myrm_agent_harness.toolkits.file_parsers.docx_embedded_assets import (
            localize_docx_embedded_markdown,
        )
        from myrm_agent_harness.toolkits.file_parsers.gfm_normalize import (
            normalize_to_gfm_markdown,
        )
        from myrm_agent_harness.toolkits.wiki.pipeline.ingress.asset_store import (
            store_asset_bytes,
        )

        parser = DocxParser()
        text = normalize_to_gfm_markdown(await parser.parse(tmp_path))
        if structure is not None and raw_relative:
            images = parser.embedded_images(tmp_path)
            if images:
                text = localize_docx_embedded_markdown(
                    text,
                    images,
                    store_asset=lambda data, content_type: store_asset_bytes(
                        structure,
                        data=data,
                        content_type=content_type,
                    ),
                    raw_relative=raw_relative,
                )
        return text or None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


async def _parse_with_tempfile(content: bytes, filename: str) -> str | None:
    from myrm_agent_harness.toolkits.file_parsers import get_parser, is_supported
    from myrm_agent_harness.toolkits.file_parsers.gfm_normalize import (
        normalize_to_gfm_markdown,
    )

    suffix = Path(filename).suffix or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        if not is_supported(tmp_path):
            return None
        parser = get_parser(tmp_path)
        text = normalize_to_gfm_markdown(await parser.parse(tmp_path))
        return text or None
    finally:
        Path(tmp_path).unlink(missing_ok=True)
