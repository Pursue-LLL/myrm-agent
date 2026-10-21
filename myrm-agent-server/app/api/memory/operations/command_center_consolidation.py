"""Memory Command Center consolidation rollback endpoints.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: 记忆管理器)
app.api.memory.utils::get_crud_memory_manager (POS: 依赖注入)

[OUTPUT]
router: `/command-center/consolidation` consolidation rollback endpoints.

[POS]
记忆合并回滚 API 操作层。将 Harness 层的 consolidation_rollback 逻辑暴露给设置页 UI。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_crud_memory_manager

router = APIRouter(prefix="/command-center/consolidation")


@router.get("/last-summary")
async def get_consolidation_last_summary(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Get the latest consolidation event summary with rollback availability status."""
    from myrm_agent_harness.toolkits.memory.strategies.consolidation_rollback import (
        get_last_consolidation_summary,
    )

    summary = await get_last_consolidation_summary(memory_manager)
    if summary is None:
        return {"available": False}
    return {"available": True, **summary}


@router.post("/rollback")
async def rollback_consolidation(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Rollback the most recent consolidation cycle."""
    from myrm_agent_harness.toolkits.memory.strategies.consolidation_rollback import (
        get_last_consolidation_summary,
        rollback_last_consolidation,
    )

    summary = await get_last_consolidation_summary(memory_manager)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No consolidation event found to rollback",
        )
    if not summary.get("rollback_available"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rollback: some memories were manually modified after consolidation",
        )

    result = await rollback_last_consolidation(memory_manager)
    return {
        "rolled_back": result.rolled_back,
        "skipped_conflict": result.skipped_conflict,
        "errors": result.errors,
        "conflict_ids": result.conflict_ids,
    }
