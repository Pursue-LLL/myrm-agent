"""Convert cloud file bytes into wiki-ready Markdown text.

[INPUT]
- app.services.files.content_extraction (POS: docx/pdf parsers)

[OUTPUT]
- bytes_to_wiki_markdown

[POS]
Shared conversion helper for Google Drive wiki source sync.
"""

from __future__ import annotations

from app.services.files.content_extraction import (
    extract_document_text_from_bytes,
    extract_pdf_text_from_bytes,
)

_TEXT_EXTENSIONS = (".md", ".txt", ".markdown")
_DOCX_EXTENSIONS = (".docx",)
_PDF_EXTENSIONS = (".pdf",)


async def bytes_to_wiki_markdown(content: bytes, *, filename: str, mime_type: str) -> str | None:
    if not content:
        return None
    lowered_name = filename.lower()
    lowered_mime = mime_type.lower()

    if lowered_mime in {"text/markdown", "text/plain"} or lowered_name.endswith(_TEXT_EXTENSIONS):
        text = content.decode("utf-8", errors="replace").strip()
        return text or None

    if (
        "wordprocessingml.document" in lowered_mime
        or lowered_name.endswith(_DOCX_EXTENSIONS)
    ):
        text = (await extract_document_text_from_bytes(content, filename=filename)).strip()
        return text or None

    if lowered_mime == "application/pdf" or lowered_name.endswith(_PDF_EXTENSIONS):
        text = (await extract_pdf_text_from_bytes(content)).strip()
        return text or None

    return None
