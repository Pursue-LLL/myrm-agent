"""Working State API — cross-session task continuity and runtime workbench endpoints.

[INPUT]
- app.api.memory.utils::get_crud_memory_manager (POS: MemoryManager factory)
- app.services.memory.consolidation_service::ConsolidationService

[OUTPUT]
- router: `/memory/working-state` read/write/clear working state & live workbench

[POS]
- 工作记忆与任务看板传输层。提供实时手边工作台快照、子任务动态流转、避坑项登记与历史任务成果摘要接口。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.api import LocalWorkingMemoryBlock
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel, Field

from app.api.memory.utils import get_crud_memory_manager
from app.services.memory.consolidation_service import ConsolidationService

WORKING_STATE_PROFILE_KEY = "__working_state"
WORKING_STATE_UPDATED_AT_KEY = "__working_state_updated_at"
WORKING_STATE_TTL_DAYS = 7

router = APIRouter(prefix="/working-state")


class WorkingStateResponse(BaseModel):
    content: str | None = None
    updated_at: str | None = None
    ttl_days: int = WORKING_STATE_TTL_DAYS
    expired: bool = False
    live_state: dict[str, object] | None = None


WORKING_STATE_MAX_LENGTH = 500


class WorkingStateUpdateRequest(BaseModel):
    content: str = Field(max_length=WORKING_STATE_MAX_LENGTH)


class SubtaskCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    subtask_id: str | None = Field(default=None, max_length=50)


class SubtaskUpdateRequest(BaseModel):
    status: Literal["pending", "in_progress", "completed", "failed", "skipped"]
    notes: str = Field(default="", max_length=500)


class TrapCreateRequest(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=200)
    avoidance_rule: str = Field(min_length=1, max_length=500)
    tool_name: str | None = Field(default=None, max_length=100)


@router.get("", response_model=WorkingStateResponse)
async def get_working_state(
    session_id: str | None = Query(None, description="Optional chat session ID for active execution state"),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> WorkingStateResponse:
    """Read current working state along with live in-memory workbench if active."""
    content = await memory_manager.get_profile_attribute(WORKING_STATE_PROFILE_KEY)
    updated_at = await memory_manager.get_profile_attribute(WORKING_STATE_UPDATED_AT_KEY)

    expired = False
    if updated_at:
        try:
            ts = datetime.fromisoformat(updated_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            expired = (datetime.now(UTC) - ts).days >= WORKING_STATE_TTL_DAYS
        except (ValueError, TypeError):
            pass

    live_state = ConsolidationService.get_live_working_state(session_id=session_id)
    return WorkingStateResponse(
        content=content,
        updated_at=updated_at,
        expired=expired,
        live_state=live_state if live_state else None,
    )


@router.put("", response_model=WorkingStateResponse)
async def update_working_state(
    body: WorkingStateUpdateRequest,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> WorkingStateResponse:
    """Manually update working state from frontend."""
    now = datetime.now(UTC).isoformat()
    await memory_manager.set_system_profile_attribute(WORKING_STATE_PROFILE_KEY, body.content)
    await memory_manager.set_system_profile_attribute(WORKING_STATE_UPDATED_AT_KEY, now)
    return WorkingStateResponse(content=body.content, updated_at=now)


@router.delete("")
async def clear_working_state(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> WorkingStateResponse:
    """Clear working state (task completed)."""
    await memory_manager.delete_system_profile_attribute(WORKING_STATE_PROFILE_KEY)
    await memory_manager.delete_system_profile_attribute(WORKING_STATE_UPDATED_AT_KEY)
    LocalWorkingMemoryBlock.reset()
    return WorkingStateResponse()


@router.get("/live")
async def get_live_workbench(
    session_id: str | None = Query(None, description="Optional chat session ID for active execution state"),
) -> dict[str, object]:
    """Retrieve active coroutine/task live working board."""
    return ConsolidationService.get_live_working_state(session_id=session_id)


@router.post("/subtasks")
async def add_workbench_subtask(body: SubtaskCreateRequest) -> dict[str, str]:
    """Add a subtask to the active workbench."""
    res = ConsolidationService.add_subtask(title=body.title, subtask_id=body.subtask_id)
    if res is None:
        raise HTTPException(status_code=400, detail="Active working state not initialized")
    return res


@router.patch("/subtasks/{subtask_id}")
async def update_workbench_subtask(subtask_id: str, body: SubtaskUpdateRequest) -> dict[str, bool]:
    """Update progress status of a subtask."""
    ok = ConsolidationService.update_subtask(
        subtask_id=subtask_id,
        status=body.status,
        notes=body.notes,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"Subtask {subtask_id} not found or not active")
    return {"success": True}


@router.post("/traps")
async def register_workbench_trap(body: TrapCreateRequest) -> dict[str, bool]:
    """Record an avoidance trap on the active workbench."""
    ConsolidationService.record_trap(
        fingerprint=body.fingerprint,
        avoidance_rule=body.avoidance_rule,
        tool_name=body.tool_name,
    )
    return {"success": True}


@router.get("/digests")
async def list_task_digests(
    limit: int = Query(default=20, ge=1, le=100),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> list[dict[str, object]]:
    """List historical consolidated task digests."""
    return await ConsolidationService.list_task_digests(memory_manager=memory_manager, limit=limit)
