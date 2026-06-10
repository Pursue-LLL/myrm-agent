"""Stream accumulation and multimodal attachment handling for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)

[OUTPUT]
- StreamAccumulator: Accumulates streaming chunks and handles multimodal attachments.

[POS]
Stream processing: accumulate LLM output chunks, detect and persist image/file attachments.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from myrm_agent_harness.toolkits.kanban.types import KanbanTask

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".svg",
        ".tiff",
        ".ico",
        ".avif",
    }
)
_PDF_EXTENSIONS = frozenset({".pdf"})
_DOCUMENT_EXTENSIONS = frozenset(
    {
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
        ".odt",
        ".ods",
        ".odp",
        ".rtf",
    }
)


@dataclass
class _StreamAccumulator:
    """Accumulates agent stream events into a final result."""

    chunks: list[str] = field(default_factory=list)
    usage: dict[str, int] | None = None
    error: str | None = None

    def add(self, event: dict[str, object]) -> None:
        event_type = event.get("type", "")
        if event_type == "message" and isinstance(event.get("data"), str):
            self.chunks.append(str(event["data"]))
        elif event_type == "message_end" and isinstance(event.get("usage"), dict):
            raw = event["usage"]
            self.usage = {str(k): _coerce_int(v) for k, v in raw.items()}
        elif event_type == "error":
            error_msg = event.get("error", "unknown agent error")
            error_type = event.get("error_type", "")
            self.error = f"{error_type}: {error_msg}" if error_type else str(error_msg)

    def to_result(self) -> tuple[bool, str]:
        if self.error:
            return False, self.error
        text = "".join(self.chunks).strip()
        if not text:
            return False, "agent returned empty response"
        return True, text


def _coerce_int(v: object) -> int:
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return 0
    return 0


def _classify_content_type(content_type: str, filename: str) -> str:
    """Classify a file as 'image', 'pdf', 'document', or 'other'."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in _IMAGE_EXTENSIONS or content_type.startswith("image/"):
        return "image"
    if ext in _PDF_EXTENSIONS or content_type == "application/pdf":
        return "pdf"
    if ext in _DOCUMENT_EXTENSIONS:
        return "document"
    return "other"


async def _load_attachment_ids(task_id: str) -> list[str]:
    from app.core.kanban.adapters.sqlalchemy_mapping import get_attachment_ids
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        m = await session.get(KanbanTaskModel, task_id)
        return get_attachment_ids(m) if m else []


async def _extract_pdf_text(file_id: str) -> str:
    try:
        from app.core.storage import files_service
        from app.services.files.content_extraction import extract_pdf_text_from_bytes

        content = await files_service.get_file_content(file_id)
        if not content:
            return ""
        return await extract_pdf_text_from_bytes(content)
    except Exception:
        logger.warning("PDF extraction failed for %s", file_id, exc_info=True)
        return ""


async def _extract_document_text(file_id: str) -> str:
    try:
        from app.core.storage import files_service
        from app.services.files.content_extraction import extract_document_text_from_bytes

        content = await files_service.get_file_content(file_id)
        if not content:
            return ""

        meta = await files_service.get_file(file_id)
        filename = getattr(meta, "filename", "") if meta else ""
        return await extract_document_text_from_bytes(content, filename=filename or "document.bin")
    except Exception:
        logger.warning("Document extraction failed for %s", file_id, exc_info=True)
        return ""


async def build_multimodal_query(
    task: KanbanTask,
    text_context: str,
    *,
    load_attachment_ids: Callable[[str], Awaitable[list[str]]] | None = None,
    extract_pdf: Callable[[str], Awaitable[str]] | None = None,
    extract_document: Callable[[str], Awaitable[str]] | None = None,
) -> str | list[dict[str, object]]:
    """Assemble a multimodal query when the task has attachments."""
    load_ids = load_attachment_ids or _load_attachment_ids
    extract_pdf_fn = extract_pdf or _extract_pdf_text
    extract_doc_fn = extract_document or _extract_document_text

    attachment_ids = await load_ids(task.task_id)
    if not attachment_ids:
        return text_context

    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.storage import files_service
    from app.services.files.attachment_settings import should_extract_document_text

    configs = await load_user_configs()
    extract_documents = should_extract_document_text(configs.personal_settings_dict)

    image_urls: list[str] = []
    extra_text_parts: list[str] = []

    for fid in attachment_ids:
        try:
            file_info = await files_service.get_file(fid)
            if file_info is None:
                logger.warning("Attachment %s not found, skipping", fid)
                continue

            kind = _classify_content_type(file_info.content_type, file_info.filename)
            content_url = f"/api/v1/files/{fid}/content"

            if kind == "image":
                image_urls.append(content_url)
            elif kind == "pdf":
                if extract_documents:
                    extracted = await extract_pdf_fn(fid)
                    if extracted:
                        extra_text_parts.append(f"\n## Attachment: {file_info.filename}\n{extracted}")
                    else:
                        extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
                else:
                    extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
            elif kind == "document":
                if extract_documents:
                    extracted = await extract_doc_fn(fid)
                    if extracted:
                        extra_text_parts.append(f"\n## Attachment: {file_info.filename}\n{extracted}")
                    else:
                        extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
                else:
                    extra_text_parts.append(f"\n[Attachment: {file_info.filename}]")
        except Exception:
            logger.warning("Failed to process attachment %s", fid, exc_info=True)

    full_text = text_context
    if extra_text_parts:
        full_text += "\n" + "\n".join(extra_text_parts)

    if not image_urls:
        return full_text

    content: list[dict[str, object]] = [{"type": "text", "text": full_text}]
    for url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": url}})
    return content
