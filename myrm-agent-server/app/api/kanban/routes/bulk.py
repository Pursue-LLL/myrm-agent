"""Kanban API routes — bulk lifecycle actions on many tasks in one request.

[INPUT]
app.api.kanban.http_common::router / get_kanban_service (POS: Kanban 共享路由与服务获取)
app.api.kanban.schemas::BulkActionRequest (POS: 批量请求体，单次 task_ids 上限 100)
app.services.kanban::KanbanService (POS: Kanban 业务编排)

[OUTPUT]
bulk_action: POST /boards/{board_id}/tasks/bulk-action，逐条返回结果、允许部分成功

[POS]
批量移动 / 归档 / 改派 / 删除的唯一入口；每个动作的单条逻辑登记在 `_BULK_HANDLERS`，路由只负责校验、逐条调用与汇总。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.kanban.http_common import get_kanban_service, router
from app.api.kanban.schemas import (
    BulkActionItemResult,
    BulkActionRequest,
    BulkActionResponse,
)
from app.services.kanban import KanbanService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

_NOT_FOUND = "Not found"

# Each handler applies one action to one task and returns the rejection reason, or None on success.
_BulkHandler = Callable[[KanbanService, str, dict[str, str]], Awaitable[str | None]]


async def _archive(svc: KanbanService, task_id: str, params: dict[str, str]) -> str | None:
    return _NOT_FOUND if await svc.move_task(task_id, TaskStatus.ARCHIVED) is None else None


async def _move(svc: KanbanService, task_id: str, params: dict[str, str]) -> str | None:
    status = params.get("status")
    if not status:
        return "Missing params.status"
    try:
        target = TaskStatus(status)
    except ValueError:
        return f"Invalid status: {status}"
    return _NOT_FOUND if await svc.move_task(task_id, target) is None else None


async def _reassign(svc: KanbanService, task_id: str, params: dict[str, str]) -> str | None:
    # The UI sends "" for "Unassigned"; the store unassigns on None and would resolve "" as an agent id.
    task = await svc.update_task(task_id, agent_id=params.get("agent_id") or None)
    return _NOT_FOUND if task is None else None


async def _delete(svc: KanbanService, task_id: str, params: dict[str, str]) -> str | None:
    return None if await svc.delete_task(task_id) else _NOT_FOUND


# The only list of supported actions: validation and dispatch cannot drift apart.
_BULK_HANDLERS: dict[str, _BulkHandler] = {
    "move": _move,
    "archive": _archive,
    "reassign": _reassign,
    "delete": _delete,
}


@router.post(
    "/boards/{board_id}/tasks/bulk-action",
    response_model=BulkActionResponse,
)
async def bulk_action(board_id: str, body: BulkActionRequest) -> BulkActionResponse:
    handler = _BULK_HANDLERS.get(body.action)
    if handler is None:
        raise HTTPException(
            400,
            f"Invalid action: {body.action}. Must be one of: {', '.join(sorted(_BULK_HANDLERS))}",
        )
    if body.action == "delete" and not body.confirm:
        raise HTTPException(400, "Bulk delete requires confirm=true")

    svc = get_kanban_service()
    results: list[BulkActionItemResult] = []

    for task_id in body.task_ids:
        try:
            error = await handler(svc, task_id, body.params)
        except ValueError as exc:
            # Business rejections (illegal transition, unmet dependencies, unknown agent) carry a reason meant for callers.
            error = str(exc)
        except Exception:
            # One broken item must not abort the batch. The traceback stays in the log; callers only get a generic reason.
            logger.exception("Bulk %s failed for task %r", body.action, task_id)
            error = "Internal error"
        results.append(BulkActionItemResult(task_id=task_id, success=error is None, error=error))

    succeeded = sum(1 for r in results if r.success)
    return BulkActionResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )
