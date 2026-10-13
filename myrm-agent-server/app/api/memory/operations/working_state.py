"""Working State API — cross-session task continuity and runtime workbench endpoints.

[INPUT]
- app.api.memory.utils::get_crud_memory_manager (POS: MemoryManager factory)
- app.services.memory.consolidation_service::ConsolidationService

[OUTPUT]
- router: `/memory/working-state` read/write/clear working state & live workbench

[POS]
- 工作记忆与任务看板传输层。提供跨会话工作状态的读取/写入/清除，以及活跃会话的实时手边工作台快照。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
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
