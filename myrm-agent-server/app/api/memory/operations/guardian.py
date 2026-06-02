"""Memory guardian endpoints — health check & manual maintenance trigger.

[INPUT]
- app.api.memory.utils::get_crud_memory_manager (POS: Per-request MemoryManager factory)
- app.lifecycle.memory_guardian::get_memory_guardian_status (POS: 记忆守护者调度器状态)
- app.lifecycle.memory_guardian::run_memory_guardian_once (POS: 按需执行记忆维护)

[OUTPUT]
- GET  /guardian/health: Memory health score + scheduler status
- POST /guardian/trigger: Manually trigger one maintenance cycle

[POS]
记忆守护者 API。暴露记忆系统健康分数和定时维护调度器状态，提供手动触发维护入口。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.memory.utils import get_crud_memory_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guardian")


@router.get("/health")
async def get_memory_health(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Return current memory health score and guardian scheduler status.

    Response includes:
    - health: 4-dimension score (freshness, coverage, retention, coherence) + total
    - guardian: scheduler status (running, last_run, next_run, intervals)
    """
    try:
        health = await memory_manager.compute_health_score()
    except Exception as exc:
        logger.warning("Memory health computation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory health computation failed",
        ) from exc

    from app.lifecycle.memory_guardian import get_memory_guardian_status

    return {
        "health": health.to_dict(),
        "guardian": get_memory_guardian_status(),
    }


@router.post("/trigger")
async def trigger_maintenance() -> dict[str, object]:
    """Manually trigger a single memory maintenance cycle.

    Respects active-session and budget guards — may skip if conditions
    are not met. Returns the resulting health score.
    """
    try:
        from app.lifecycle.memory_guardian import run_memory_guardian_once

        result = await run_memory_guardian_once()
        return result
    except Exception as exc:
        logger.error("Manual maintenance trigger failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Maintenance trigger failed: {exc!s}",
        ) from exc
