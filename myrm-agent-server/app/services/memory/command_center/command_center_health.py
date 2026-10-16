"""Memory health snapshot for the memory command center.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager, MemoryOperationKind, MemoryOperationStatus (POS: Unified memory manager and ledger enums)
app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本服务)
app.lifecycle.memory_guardian::get_memory_guardian_status (POS: 记忆守护进程状态)

[OUTPUT]
build_health: cached or freshly computed memory health with guardian status; a refresh persists the snapshot and a ledger event.
health_status: maps a 0-100 score to the healthy / degraded / critical / unknown bucket.

[POS]
个人大脑指挥中心的健康投影。优先读 TTL 内的账本快照；强制刷新或快照过期时重新计算健康分、读取守护进程状态，并把快照与健康检查事件写回账本。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import MemoryCommandHealth
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

logger = logging.getLogger(__name__)

HEALTH_TTL_SECONDS = 300

HealthStatus = Literal["healthy", "degraded", "critical", "unknown"]


def health_status(score: int | None) -> HealthStatus:
    if score is None:
        return "unknown"
    if score >= 80:
        return "healthy"
    if score >= 55:
        return "degraded"
    return "critical"


def _to_int(value: object) -> int:
    """Strict int coercion: unsupported types raise so the caller degrades to an unknown score."""
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"Cannot interpret {type(value).__name__} as an integer")


async def build_health(
    *,
    db: AsyncSession,
    ledger: MemoryOperationLedgerService,
    memory_manager: MemoryManager,
    force_refresh: bool = False,
) -> MemoryCommandHealth:
    cached = await ledger.get_fresh_health_snapshot(ttl_seconds=HEALTH_TTL_SECONDS)
    if cached is not None and not force_refresh:
        return MemoryCommandHealth(
            status=health_status(cached.total),
            total=cached.total,
            dimensions=cached.dimensions_json,
            suggestions=cached.suggestions_json,
            has_graph=cached.has_graph,
            sample_size=cached.sample_size,
            guardian_running=cached.guardian_running,
            seconds_until_next=cached.seconds_until_next,
            checked_at=cached.checked_at,
            cache_status="fresh",
        )

    total: int | None = None
    dimensions: dict[str, float] = {}
    suggestions: list[str] = []
    has_graph = memory_manager.has_graph
    sample_size = 0

    try:
        health_dict = (await memory_manager.compute_health_score()).to_dict()
        total = _to_int(health_dict.get("total", 0))
        raw_dimensions = health_dict.get("dimensions", {})
        if isinstance(raw_dimensions, dict):
            dimensions = {str(key): float(value) for key, value in raw_dimensions.items() if isinstance(value, (int, float))}
        raw_suggestions = health_dict.get("suggestions", [])
        if isinstance(raw_suggestions, list):
            suggestions = [str(item) for item in raw_suggestions]
        has_graph = bool(health_dict.get("has_graph", has_graph))
        sample_size = _to_int(health_dict.get("sample_size", 0))
    except Exception as exc:
        logger.warning("Memory health snapshot failed: %s", exc)
        total = None

    guardian_running = False
    seconds_until_next: int | None = None
    try:
        from app.lifecycle.memory_guardian import get_memory_guardian_status

        guardian = get_memory_guardian_status()
        guardian_running = bool(guardian.get("running", False))
        raw_next = guardian.get("seconds_until_next")
        if isinstance(raw_next, int):
            seconds_until_next = raw_next
    except Exception as exc:
        logger.warning("Memory guardian status unavailable: %s", exc)
        guardian_running = False

    status = health_status(total)
    health = MemoryCommandHealth(
        status=status,
        total=total,
        dimensions=dimensions,
        suggestions=suggestions,
        has_graph=has_graph,
        sample_size=sample_size,
        guardian_running=guardian_running,
        seconds_until_next=seconds_until_next,
        checked_at=datetime.now(UTC),
        cache_status="refreshed",
    )
    await ledger.save_health_snapshot(
        status=status,
        total=total,
        dimensions=dimensions,
        suggestions=suggestions,
        has_graph=has_graph,
        sample_size=sample_size,
        guardian_running=guardian_running,
        seconds_until_next=seconds_until_next,
        ttl_seconds=HEALTH_TTL_SECONDS,
    )
    await ledger.record_event(
        kind=MemoryOperationKind.HEALTH_CHECK,
        status=(MemoryOperationStatus.SUCCESS if total is not None else MemoryOperationStatus.WARNING),
        summary="Memory health snapshot refreshed.",
        source="memory_command_center",
        target_kind="health",
        metadata={"health_score": total, "cache_ttl_seconds": HEALTH_TTL_SECONDS},
    )
    await db.commit()
    return health
