"""Kanban HTTP shared router, converters, and attachment helpers.

[INPUT]
app.services.kanban::KanbanService (POS: Kanban 业务编排)
app.core.kanban.adapters.sqlalchemy_mapping (POS: 附件 ID 持久化字段)

[OUTPUT]
router / get_kanban_service / 附件与 TaskResponse 转换辅助函数

[POS]
Kanban API 共享路由与 DTO 装配；`routes/*` 仅注册端点。
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter
from myrm_agent_harness.toolkits.kanban.types import KanbanBoard, KanbanTask

from app.api.kanban.schemas import AttachmentInfo, BoardResponse, TaskResponse
from app.core.kanban.adapters.sqlalchemy_mapping import (
    get_attachment_ids,
    set_attachment_ids,
)
from app.services.kanban import KanbanService
from app.services.kanban.diagnostics import create_diagnostic_engine

router = APIRouter(prefix="/kanban", tags=["kanban"])

diag_engine = create_diagnostic_engine()


def get_kanban_service() -> KanbanService:
    return KanbanService.get_instance()


async def _load_task_attachment_ids(task_id: str) -> list[str]:
    """Load attachment IDs from the DB for a task."""
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        m = await session.get(KanbanTaskModel, task_id)
        return get_attachment_ids(m) if m else []


async def _batch_load_attachment_ids(task_ids: list[str]) -> dict[str, list[str]]:
    """Batch-load attachment IDs for multiple tasks (avoids N+1)."""
    if not task_ids:
        return {}
    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        stmt = select(
            KanbanTaskModel.id,
            KanbanTaskModel.attachment_ids_json,
        ).where(
            KanbanTaskModel.id.in_(task_ids),
            KanbanTaskModel.attachment_ids_json.is_not(None),
        )
        rows = (await session.execute(stmt)).all()
        return {r[0]: list(r[1]) for r in rows if r[1]}


async def _save_task_attachment_ids(task_id: str, ids: list[str]) -> None:
    """Persist attachment IDs on a task row."""
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        m = await session.get(KanbanTaskModel, task_id)
        if m:
            set_attachment_ids(m, ids)
            await session.commit()


async def _task_response_with_attachments(task: KanbanTask) -> TaskResponse:
    """Build a TaskResponse with attachment info resolved from DB."""
    att_ids = await _load_task_attachment_ids(task.task_id)
    return await _task_to_response(task, attachment_ids=att_ids)


def _board_to_response(board: KanbanBoard) -> BoardResponse:
    return BoardResponse(
        board_id=board.board_id,
        name=board.name,
        description=board.description,
        settings={
            "max_concurrent_tasks": board.settings.max_concurrent_tasks,
            "heartbeat_interval_seconds": board.settings.heartbeat_interval_seconds,
            "zombie_timeout_seconds": board.settings.zombie_timeout_seconds,
            "max_retries_per_task": board.settings.max_retries_per_task,
            "auto_block_after_consecutive_failures": board.settings.auto_block_after_consecutive_failures,
            "specify_max_tokens": board.settings.specify_max_tokens,
            "auto_specify_on_create": board.settings.auto_specify_on_create,
            "default_workdir": board.settings.default_workdir,
        },
        created_at=board.created_at,
        updated_at=board.updated_at,
    )


async def _resolve_attachments(ids: list[str]) -> list[AttachmentInfo]:
    """Resolve file IDs to attachment metadata for display (concurrent)."""
    if not ids:
        return []

    from app.core.storage import files_service

    async def _resolve_one(fid: str) -> AttachmentInfo:
        url = f"/api/v1/files/{fid}/content"
        filename = fid
        content_type = "application/octet-stream"
        try:
            info = await files_service.get_file(fid)
            if info:
                filename = getattr(info, "filename", fid)
                content_type = getattr(info, "content_type", content_type)
        except Exception:
            pass
        return AttachmentInfo(
            file_id=fid,
            filename=filename,
            content_type=content_type,
            url=url,
        )

    return list(await asyncio.gather(*(_resolve_one(fid) for fid in ids)))


async def _task_to_response(
    task: KanbanTask,
    *,
    attachment_ids: list[str] | None = None,
) -> TaskResponse:
    ids = attachment_ids or []
    attachments = await _resolve_attachments(ids)
    criteria = task.metadata.get("completion_criteria")
    return TaskResponse(
        task_id=task.task_id,
        board_id=task.board_id,
        title=task.title,
        description=task.description,
        status=task.status.value,
        priority=task.priority.value,
        agent_id=task.agent_id,
        goal_id=task.goal_id,
        parent_task_id=task.parent_task_id,
        workspace_path=task.workspace_path,
        branch=task.branch,
        retry_count=task.retry_count,
        max_retries=task.max_retries,
        consecutive_failures=task.consecutive_failures,
        blocked_reason=task.blocked_reason,
        block_kind=task.block_kind.value if task.block_kind else None,
        scheduled_until=task.scheduled_until,
        progress_note=task.progress_note,
        result=task.result,
        error=task.error,
        metadata=task.metadata,
        extra_skill_ids=task.extra_skill_ids,
        attachment_ids=ids,
        attachments=attachments,
        max_runtime_seconds=task.max_runtime_seconds,
        completion_criteria=criteria if isinstance(criteria, (str, list)) else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
        completed_at=task.completed_at,
    )
