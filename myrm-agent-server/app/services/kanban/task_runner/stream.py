"""Stream accumulation and multimodal attachment handling for KanbanTaskRunner.

[INPUT]
- myrm_agent_harness.toolkits.kanban.types (POS: Kanban domain types.)
- myrm_agent_harness.agent.streaming.answer_draft::AnswerDraft (POS: Streamed answer text honouring the restart contract)
- myrm_agent_harness.api::AgentEventType (POS: Stream event types)
- app.services.agent.approval_payload::is_tool_stuck_pause, is_browser_takeover_request (POS: Tell a loop guard pause and a browser step that needs a person from an approval)
- app.services.kanban.task_runner.outcomes::APPROVAL_NEEDED_BLOCK_REASON, TAKEOVER_NEEDED_BLOCK_REASON (POS: The block reasons of the two requests nobody can answer)
- app.core.storage.files_service (POS: 文件存储 SSOT；附件字节读取 via get_content)

[OUTPUT]
- _StreamAccumulator: Accumulates agent stream events (answer text, usage, cost, error, the request the run stopped on) into a final result.
- build_multimodal_query: Assembles text or multimodal query from task attachments.

[POS]
Stream processing: accumulate LLM output chunks, detect and persist image/file attachments; build Kanban agent query with PDF/Office text extraction.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from myrm_agent_harness.agent.streaming.answer_draft import AnswerDraft
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.services.agent.approval_payload import is_browser_takeover_request, is_tool_stuck_pause
from app.services.kanban.task_runner.outcomes import APPROVAL_NEEDED_BLOCK_REASON, TAKEOVER_NEEDED_BLOCK_REASON

logger = logging.getLogger(__name__)

# Both end the stream on an interrupt that waits for an answer; a kanban run has nobody to give it.
_APPROVAL_STOP_EVENTS = frozenset({AgentEventType.TOOL_APPROVAL_REQUEST.value, AgentEventType.APPROVAL_REQUIRED.value})

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

    answer: AnswerDraft = field(default_factory=AnswerDraft)
    usage: dict[str, int] | None = None
    cost_usd: float | None = None
    error: str | None = None
    request_reason: str | None = None

    @property
    def unanswered_request_reason(self) -> str | None:
        """The block reason of the request the run ended on instead of failing: a run error outranks it."""
        return self.request_reason if self.error is None else None

    def add(self, event: dict[str, object]) -> None:
        event_type = event.get("type", "")
        self.answer.feed(event)
        data = event.get("data")
        if event_type == "token_usage" and isinstance(data, dict):
            usage = data.get("usage")
            if isinstance(usage, dict):
                self.usage = {str(k): _coerce_int(v) for k, v in usage.items()}
            cost = data.get("cost_usd")
            if isinstance(cost, (int, float)):
                self.cost_usd = (self.cost_usd or 0.0) + float(cost)
        elif event_type == "message_end":
            end_usage = event.get("usage")
            if isinstance(end_usage, dict):
                self.usage = {str(k): _coerce_int(v) for k, v in end_usage.items()}
            cost = event.get("cost_usd")
            if isinstance(cost, (int, float)):
                self.cost_usd = float(cost)
        elif event_type == "error":
            error_msg = event.get("error", "unknown agent error")
            error_type = event.get("error_type", "")
            self.error = f"{error_type}: {error_msg}" if error_type else str(error_msg)
        elif event_type in _APPROVAL_STOP_EVENTS and not is_tool_stuck_pause(data) and self.request_reason is None:
            # The loop guard's pause arrives as ``approval_required`` too, but it reports a failure and asks for no approval.
            # The first request names the reason; the run is held for a person either way.
            self.request_reason = (
                TAKEOVER_NEEDED_BLOCK_REASON if is_browser_takeover_request(data) else APPROVAL_NEEDED_BLOCK_REASON
            )

    def to_result(self) -> tuple[bool, str]:
        if self.error:
            return False, self.error
        text = self.answer.text.strip()
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

        content = await files_service.get_content(file_id)
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

        content = await files_service.get_content(file_id)
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
