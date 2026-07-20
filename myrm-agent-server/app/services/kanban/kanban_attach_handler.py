"""Kanban worker attach handler — persists task attachments via files service.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::KanbanStore (POS: Kanban persistence.)
- app.services.kanban.task_attachment_ids (POS: Kanban task attachment ID persistence.)

[OUTPUT]
- create_kanban_attach_handler: Factory returning harness KanbanTaskAttachFn callback.

[POS]
Server-side implementation for kanban_attach LLM tool (SSRF-safe URL fetch + path ingest).
"""

from __future__ import annotations

import logging
import mimetypes
import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from myrm_agent_harness.api import KanbanStore
from myrm_agent_harness.core.security.guards.ssrf import async_validate_url_for_ssrf
from myrm_agent_harness.core.security.http.secure_fetch import secure_get
from myrm_agent_harness.toolkits.kanban.kanban_agent_tools import KanbanTaskAttachFn
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.core.storage.models import File
from app.services.kanban.task_runner_worktree import resolve_base_dir

logger = logging.getLogger(__name__)

_MAX_ATTACHMENTS = 10
_MAX_ATTACH_BYTES = 20 * 1024 * 1024


def create_kanban_attach_handler(store: KanbanStore) -> KanbanTaskAttachFn:
    """Build attach callback wired into harness create_kanban_tools(worker mode)."""

    async def attach_task_file(
        task_id: str,
        source: Literal["path", "url"],
        value: str,
    ) -> dict[str, object]:
        from app.services.kanban.task_attachment_ids import (
            load_task_attachment_ids,
            save_task_attachment_ids,
        )

        task = await store.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        existing = await load_task_attachment_ids(task_id)
        if len(existing) >= _MAX_ATTACHMENTS:
            raise ValueError(f"Task already has the maximum of {_MAX_ATTACHMENTS} attachments")

        if source == "path":
            file_obj = await _attach_from_path(store, task_id, task, value)
        else:
            file_obj = await _attach_from_url(task_id, value)

        updated_ids = [*existing, file_obj.id]
        await save_task_attachment_ids(task_id, updated_ids)
        return {
            "file_id": file_obj.id,
            "filename": file_obj.filename,
            "mime_type": file_obj.content_type,
            "size_bytes": file_obj.size,
            "attachment_count": len(updated_ids),
        }

    return attach_task_file


async def _attach_from_path(
    store: KanbanStore,
    task_id: str,
    task: KanbanTask,
    raw_path: str,
) -> File:
    from app.core.storage import files_service

    base_dir = await resolve_base_dir(store, task)
    if not base_dir:
        raise ValueError("Task has no workspace path — cannot attach local files")

    candidate = Path(raw_path).expanduser()
    if not candidate.is_absolute():
        candidate = Path(base_dir) / candidate
    candidate = candidate.resolve()

    base_resolved = Path(base_dir).resolve()
    if not str(candidate).startswith(str(base_resolved) + os.sep) and candidate != base_resolved:
        raise ValueError("Path must be inside the task workspace")

    if not candidate.is_file():
        raise ValueError(f"File not found: {raw_path}")

    size = candidate.stat().st_size
    if size > _MAX_ATTACH_BYTES:
        raise ValueError(f"File exceeds {_MAX_ATTACH_BYTES} byte limit")

    content = candidate.read_bytes()
    filename = candidate.name
    content_type, _ = mimetypes.guess_type(filename)
    file_obj = await files_service.save_generated_file(
        filename=filename,
        content=content,
        content_type=content_type,
        source_chat_id=f"kanban:{task_id}",
    )
    logger.info("kanban_attach path task=%s file=%s bytes=%s", task_id[:8], file_obj.id, size)
    return file_obj


async def _attach_from_url(task_id: str, url: str) -> File:
    from app.core.storage import files_service

    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("Only HTTPS URLs are allowed for kanban_attach")

    ssrf = await async_validate_url_for_ssrf(url)
    if not ssrf.safe:
        raise ValueError(ssrf.error or "URL blocked by SSRF policy")

    response = await secure_get(url)
    if response.status_code >= 400:
        raise ValueError(f"Failed to fetch URL (HTTP {response.status_code})")

    content = response.content
    if len(content) > _MAX_ATTACH_BYTES:
        raise ValueError(f"Download exceeds {_MAX_ATTACH_BYTES} byte limit")

    filename = Path(parsed.path).name or "attachment.bin"
    content_type = response.content_type or mimetypes.guess_type(filename)[0]
    file_obj = await files_service.save_generated_file(
        filename=filename,
        content=content,
        content_type=content_type,
        source_chat_id=f"kanban:{task_id}",
    )
    logger.info("kanban_attach url task=%s file=%s bytes=%s", task_id[:8], file_obj.id, len(content))
    return file_obj
