"""[INPUT]
- app.core.storage::files_service (POS: stored file metadata and content access)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..documents::_parse_stored_document / _DOCUMENT_EXTENSIONS / _BINARY_EXTENSIONS (POS: Office parsing + file classification)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- _stored_file_part: render one stored upload/generated file as a mention fragment
- stored_file_part: @uploaded-file / @generated-file handler

[POS]
Uploaded and generated file @ references. The handler works from storage rather than the workspace,
so a file the user dropped in this turn is readable even before it lands on disk.
"""

from __future__ import annotations

from pathlib import Path

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..documents import _BINARY_EXTENSIONS, _DOCUMENT_EXTENSIONS, _parse_stored_document
from ..xml import _can_inline, _format_size, _xml_error, _xml_metadata, _xml_part


async def _stored_file_part(ref: MentionReferenceRequest, current_total_bytes: int) -> tuple[str, int]:
    from app.core.storage import files_service

    if not ref.file_id:
        return _xml_error(ref.label or ref.type, "missing file_id"), 0

    file = await files_service.get_file_by_id(ref.file_id)
    if file is None:
        return _xml_error(ref.label or ref.file_id, "file not found"), 0

    content = await files_service.get_file_content_by_path(file.storage_path)
    display_path = ref.label or file.filename
    if content is None:
        return _xml_error(display_path, "file content not found"), 0

    ext = Path(file.filename).suffix.lower()
    if ext in _DOCUMENT_EXTENSIONS or ext == ".pdf":
        parsed = await _parse_stored_document(content, ext, file.filename)
        if parsed:
            parsed_bytes = len(parsed.encode("utf-8"))
            if _can_inline(parsed_bytes, current_total_bytes):
                return _xml_part(display_path, "document", parsed), parsed_bytes
            return (
                _xml_metadata(
                    display_path,
                    "document",
                    f"Document too large ({_format_size(parsed_bytes)}), use file_read_tool to inspect if needed.",
                ),
                0,
            )
        return (
            _xml_metadata(
                display_path,
                "document",
                f"No extractable text ({_format_size(file.size)}), use file_read_tool to inspect if needed.",
            ),
            0,
        )

    if ext in _BINARY_EXTENSIONS:
        return (
            _xml_metadata(
                display_path,
                "binary",
                f"Binary file ({_format_size(file.size)}), use file_read_tool to inspect if needed.",
            ),
            0,
        )

    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return (
            _xml_metadata(display_path, "binary", f"Binary file ({_format_size(file.size)})"),
            0,
        )

    text_bytes = len(text.encode("utf-8"))
    if _can_inline(text_bytes, current_total_bytes):
        return _xml_part(display_path, "stored-text", text), text_bytes
    return (
        _xml_metadata(
            display_path,
            "stored-text",
            f"Content too large to inline ({_format_size(text_bytes)})",
        ),
        0,
    )


async def stored_file_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    part, consumed_bytes = await _stored_file_part(ref, ctx.total_bytes)
    ctx.parts.append(part)
    ctx.total_bytes += consumed_bytes
