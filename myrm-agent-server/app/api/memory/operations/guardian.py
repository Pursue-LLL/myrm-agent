"""Memory guardian endpoints — health check, manual triggers, pattern discovery.

[INPUT]
- app.api.memory.utils::get_crud_memory_manager (POS: Per-request MemoryManager factory)
- app.lifecycle.memory_guardian::get_memory_guardian_status (POS: 记忆守护者调度器状态)
- app.lifecycle.memory_guardian::run_memory_guardian_once (POS: 按需执行记忆维护)
- app.lifecycle.memory_guardian::run_pattern_discovery_once (POS: 按需执行行为模式发现)

[OUTPUT]
- GET  /guardian/health: Memory health score + scheduler status
- POST /guardian/trigger: Manually trigger one maintenance cycle
- GET  /guardian/pattern-discoveries: Recent pattern discovery results
- POST /guardian/trigger-pattern-discovery: Manually trigger pattern discovery

[POS]
记忆守护者 API。暴露记忆系统健康分数和定时维护调度器状态，提供手动触发维护入口，
以及行为模式发现历史查询和手动触发。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from myrm_agent_harness.toolkits.memory import MemoryManager
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.database.models.memory import MemoryOperationEventModel

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


@router.get("/pattern-discoveries")
async def get_pattern_discoveries(
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, object]]:
    """Return recent pattern discovery results from the operation ledger.

    Each entry contains the full PatternReport metadata including
    discovered patterns, confidence scores, and meta observation.
    """
    result = await db.execute(
        select(MemoryOperationEventModel)
        .where(MemoryOperationEventModel.source == "pattern_discovery")
        .order_by(desc(MemoryOperationEventModel.occurred_at))
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": row.id,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "summary": row.summary,
            "metadata": row.metadata_json if row.metadata_json else {},
        }
        for row in rows
    ]


@router.post("/trigger-pattern-discovery")
async def trigger_pattern_discovery() -> dict[str, object]:
    """Manually trigger a pattern discovery cycle.

    Respects the harness-layer maturity gate (>= 50 memories, >= 3
    consolidations). Returns skip reason if not ready.
    """
    try:
        from app.lifecycle.memory_guardian import run_pattern_discovery_once

        result = await run_pattern_discovery_once()
        return result
    except Exception as exc:
        logger.error("Pattern discovery trigger failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pattern discovery trigger failed: {exc!s}",
        ) from exc
