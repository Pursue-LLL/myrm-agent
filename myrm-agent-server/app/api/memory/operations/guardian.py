"""Memory guardian endpoints — health check, manual triggers, pattern discovery.

[INPUT]
- app.api.memory.utils::get_crud_memory_manager (POS: Per-request MemoryManager factory)
- app.lifecycle.memory_guardian::get_memory_guardian_status (POS: 记忆守护者调度器状态)
- app.lifecycle.memory_guardian::run_memory_guardian_once (POS: 按需执行记忆维护)
- app.lifecycle.memory_guardian::run_pattern_discovery_once (POS: 按需执行行为模式发现)

[OUTPUT]
- GET  /guardian/health: Memory health score + scheduler status
- GET  /guardian/overview: Consolidated health/policy/alerts + morning digest
- POST /guardian/trigger: Manually trigger one maintenance cycle (`safe` / `force`)
- GET  /guardian/policy: Read guardian schedule policy
- PUT  /guardian/policy: Update guardian schedule policy
- GET  /guardian/morning-digest: Latest completed maintenance-window digest for morning review
- GET  /guardian/pattern-discoveries: Recent pattern discovery results
- POST /guardian/trigger-pattern-discovery: Manually trigger pattern discovery

[POS]
记忆守护者 API。暴露记忆系统健康分数和调度器状态，提供 `safe/force` 手动维护触发、
受约束策略配置（频率档位 + quiet window）、晨间摘要读取，以及行为模式发现历史查询和手动触发。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from myrm_agent_harness.toolkits.memory import MemoryManager
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.database.models.memory import MemoryOperationEventModel
from app.services.memory.guardian_policy import (
    MemoryGuardianPolicy,
    ensure_memory_guardian_timezone_initialized,
    load_memory_guardian_policy,
    save_memory_guardian_policy,
)
from app.services.memory.operation_ledger import (
    MemoryOperationLedgerService,
    guardian_guard_alert_thresholds,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guardian")


class MemoryGuardianTriggerRequest(BaseModel):
    mode: Literal["safe", "force"] = "safe"


def _parse_client_timezone_offset_minutes(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    try:
        return int(raw_value)
    except ValueError:
        return None


def _server_local_timezone_offset_minutes() -> int:
    local_offset = datetime.now().astimezone().utcoffset()
    if local_offset is None:
        return 0
    minutes = int(local_offset.total_seconds() // 60)
    return max(-720, min(840, minutes))


async def _resolve_guardian_policy(request: Request) -> MemoryGuardianPolicy:
    offset = _parse_client_timezone_offset_minutes(request.headers.get("x-client-timezone-offset-minutes"))
    if offset is None:
        offset = _parse_client_timezone_offset_minutes(request.headers.get("x-timezone-offset-minutes"))
    if offset is None:
        offset = _parse_client_timezone_offset_minutes(request.query_params.get("timezone_offset_minutes"))
    if offset is not None:
        return await ensure_memory_guardian_timezone_initialized(offset, source="client_header")

    policy = await load_memory_guardian_policy()
    if policy.timezone_initialized:
        return policy
    try:
        return await ensure_memory_guardian_timezone_initialized(
            _server_local_timezone_offset_minutes(),
            source="server_fallback",
        )
    except Exception as exc:
        logger.warning("Guardian timezone fallback bootstrap failed: %s", exc)
        return policy


def _default_guard_alert_snapshot(*, frequency_tier: str) -> dict[str, object]:
    thresholds = guardian_guard_alert_thresholds(frequency_tier=frequency_tier)
    return {
        "active": False,
        "escalated": False,
        "window_hours": 24,
        "total": 0,
        "reasons": {},
        "dominant_reason": None,
        "dominant_reason_count": 0,
        "dominant_reason_ratio": 0.0,
        "thresholds": thresholds,
        "last_occurred_at": None,
    }


async def _build_guardian_health_payload(
    request: Request,
    *,
    memory_manager: MemoryManager,
    db: AsyncSession,
) -> tuple[dict[str, object], MemoryGuardianPolicy]:
    """Build health/policy/alert payload shared by health and overview endpoints."""
    try:
        health = await memory_manager.compute_health_score()
    except Exception as exc:
        logger.warning("Memory health computation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Memory health computation failed",
        ) from exc

    from app.lifecycle.memory_guardian import get_memory_guardian_status

    policy = await _resolve_guardian_policy(request)
    alerts = {"guard_unavailable": _default_guard_alert_snapshot(frequency_tier=policy.frequency_tier)}
    try:
        alerts["guard_unavailable"] = await MemoryOperationLedgerService(db).guardian_guard_alert_snapshot(
            lookback_hours=24,
            frequency_tier=policy.frequency_tier,
        )
    except Exception as exc:
        logger.warning("Guardian alert snapshot query failed: %s", exc)

    payload = {
        "health": health.to_dict(),
        "guardian": get_memory_guardian_status(policy=policy),
        "policy": policy.model_dump(),
        "alerts": alerts,
    }
    return payload, policy


@router.get("/health")
async def get_memory_health(
    request: Request,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return current memory health score and guardian scheduler status."""
    payload, _policy = await _build_guardian_health_payload(
        request,
        memory_manager=memory_manager,
        db=db,
    )
    return payload


@router.get("/overview")
async def get_memory_guardian_overview(
    request: Request,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return consolidated guardian health + digest payload for settings pages."""
    payload, policy = await _build_guardian_health_payload(
        request,
        memory_manager=memory_manager,
        db=db,
    )
    digest: dict[str, object]
    try:
        digest = await MemoryOperationLedgerService(db).latest_guardian_morning_digest(policy=policy)
    except Exception as exc:
        logger.warning("Guardian overview digest query failed: %s", exc)
        digest = {"available": False}
    payload["digest"] = digest
    return payload


@router.post("/trigger")
async def trigger_maintenance(payload: MemoryGuardianTriggerRequest | None = None) -> dict[str, object]:
    """Manually trigger a single memory maintenance cycle.

    - safe mode (default): respects quiet-window / active-session / budget / capacity guards.
    - force mode: bypasses guards and executes one deterministic maintenance cycle.
    """
    try:
        from app.lifecycle.memory_guardian import run_memory_guardian_once

        mode = payload.mode if payload is not None else "safe"
        result = await run_memory_guardian_once(mode=mode)
        return result
    except Exception as exc:
        logger.error("Manual maintenance trigger failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Maintenance trigger failed: {exc!s}",
        ) from exc


@router.get("/policy")
async def get_guardian_policy() -> dict[str, object]:
    """Return the persisted Memory Guardian scheduling policy."""
    policy = await load_memory_guardian_policy()
    return policy.model_dump()


@router.put("/policy")
async def update_guardian_policy(policy: MemoryGuardianPolicy) -> dict[str, object]:
    """Update Memory Guardian scheduling policy."""
    saved = await save_memory_guardian_policy(policy)
    return saved.model_dump()


@router.get("/morning-digest")
async def get_guardian_morning_digest(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, object]:
    """Return the latest completed maintenance-window digest for morning review."""
    policy = await _resolve_guardian_policy(request)
    return await MemoryOperationLedgerService(db).latest_guardian_morning_digest(policy=policy)


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
