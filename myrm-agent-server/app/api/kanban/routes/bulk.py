"""Kanban API routes — bulk."""

from __future__ import annotations

import logging

from fastapi import HTTPException
from myrm_agent_harness.toolkits.kanban.types import (
    TaskStatus,
)

from app.api.kanban.http_common import (
    get_kanban_service,
    router,
)
from app.api.kanban.schemas import (
    BulkActionItemResult,
    BulkActionRequest,
    BulkActionResponse,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bulk actions
# ---------------------------------------------------------------------------

_BULK_VALID_ACTIONS = {"move", "archive", "reassign", "delete"}


@router.post(
    "/boards/{board_id}/tasks/bulk-action",
    response_model=BulkActionResponse,
)
async def bulk_action(board_id: str, body: BulkActionRequest) -> BulkActionResponse:
    if body.action not in _BULK_VALID_ACTIONS:
        raise HTTPException(
            400,
            f"Invalid action: {body.action}. Must be one of: {', '.join(sorted(_BULK_VALID_ACTIONS))}",
        )
    if body.action == "delete" and not body.confirm:
        raise HTTPException(400, "Bulk delete requires confirm=true")

    svc = get_kanban_service()
    results: list[BulkActionItemResult] = []

    for task_id in body.task_ids:
        try:
            if body.action == "archive":
                task = await svc.move_task(task_id, TaskStatus.ARCHIVED)
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "move":
                status_str = body.params.get("status")
                if not status_str:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Missing params.status"))
                    continue
                try:
                    target = TaskStatus(status_str)
                except ValueError:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error=f"Invalid status: {status_str}"))
                    continue
                task = await svc.move_task(task_id, target)
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "reassign":
                # The UI sends "" for "Unassigned"; the store unassigns on None and would resolve "" as an agent id.
                agent_id = body.params.get("agent_id") or None
                task = await svc.update_task(task_id, agent_id=agent_id)
                if task is None:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

            elif body.action == "delete":
                deleted = await svc.delete_task(task_id)
                if not deleted:
                    results.append(BulkActionItemResult(task_id=task_id, success=False, error="Not found"))
                else:
                    results.append(BulkActionItemResult(task_id=task_id, success=True))

        except ValueError as exc:
            # Business rejections (illegal transition, unmet dependencies, unknown agent) carry a reason meant for callers.
            results.append(BulkActionItemResult(task_id=task_id, success=False, error=str(exc)))
        except Exception:
            # One broken item must not abort the batch. The traceback stays in the log; callers only get a generic reason.
            logger.exception("Bulk %s failed for task %r", body.action, task_id)
            results.append(BulkActionItemResult(task_id=task_id, success=False, error="Internal error"))

    succeeded = sum(1 for r in results if r.success)
    return BulkActionResponse(
        results=results,
        total=len(results),
        succeeded=succeeded,
        failed=len(results) - succeeded,
    )
