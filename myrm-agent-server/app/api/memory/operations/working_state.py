"""Working State API — cross-session task continuity endpoint.

[INPUT]
- app.api.memory.utils::get_crud_memory_manager (POS: MemoryManager factory)

[OUTPUT]
- router: `/memory/working-state` read/write/clear working state

[POS]
Thin transport layer for Working Memory (cross-session task progress).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel, Field

from app.api.memory.utils import get_crud_memory_manager

WORKING_STATE_PROFILE_KEY = "__working_state"
WORKING_STATE_UPDATED_AT_KEY = "__working_state_updated_at"
WORKING_STATE_TTL_DAYS = 7

router = APIRouter(prefix="/working-state")


class WorkingStateResponse(BaseModel):
    content: str | None = None
    updated_at: str | None = None
    ttl_days: int = WORKING_STATE_TTL_DAYS
    expired: bool = False


WORKING_STATE_MAX_LENGTH = 500


class WorkingStateUpdateRequest(BaseModel):
    content: str = Field(max_length=WORKING_STATE_MAX_LENGTH)


@router.get("", response_model=WorkingStateResponse)
async def get_working_state(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> WorkingStateResponse:
    """Read current working state."""
    content = await memory_manager.get_profile_attribute(WORKING_STATE_PROFILE_KEY)
    updated_at = await memory_manager.get_profile_attribute(WORKING_STATE_UPDATED_AT_KEY)

    if not content:
        return WorkingStateResponse()

    expired = False
    if updated_at:
        try:
            ts = datetime.fromisoformat(updated_at)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            expired = (datetime.now(UTC) - ts).days >= WORKING_STATE_TTL_DAYS
        except (ValueError, TypeError):
            pass

    return WorkingStateResponse(content=content, updated_at=updated_at, expired=expired)


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
    return WorkingStateResponse()
