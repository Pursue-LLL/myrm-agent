"""Memory Command Center consolidation undo endpoints.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: 记忆管理器)
myrm_agent_harness.toolkits.memory.strategies.consolidation_undo::{UndoResult, UndoSummary, get_undo_summary, undo_last_consolidation} (POS: 最近一次记忆自动整理的精确撤销)
app.api.memory.utils::get_crud_memory_manager (POS: 依赖注入)

[OUTPUT]
router: `/command-center/consolidation` consolidation undo endpoints.

[POS]
记忆自动整理撤销 API 操作层。把 Harness 层的 consolidation_undo 暴露给设置页 UI：读取可撤销的最近一次整理，按 cycle_id 撤销它。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.consolidation_undo import (
    UndoResult,
    UndoSummary,
    get_undo_summary,
    undo_last_consolidation,
)
from pydantic import BaseModel

from app.api.memory.utils import get_crud_memory_manager

router = APIRouter(prefix="/command-center/consolidation")


class ConsolidationUndoState(BaseModel):
    """The cycle the settings card offers to undo; an object, because the client treats a bare null body as an error."""

    summary: UndoSummary | None = None


class ConsolidationUndoRequest(BaseModel):
    cycle_id: str


@router.get("/undo", response_model=ConsolidationUndoState)
async def get_consolidation_undo(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ConsolidationUndoState:
    """Describe the latest consolidation cycle that can still be undone."""
    return ConsolidationUndoState(summary=await get_undo_summary(memory_manager))


@router.post("/undo", response_model=UndoResult)
async def undo_consolidation(
    body: ConsolidationUndoRequest,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> UndoResult:
    """Undo the consolidation cycle the caller was shown; a cycle that is gone or was replaced is a conflict."""
    result = await undo_last_consolidation(memory_manager, body.cycle_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This consolidation can no longer be undone: it was already undone or a newer one replaced it",
        )
    return result
