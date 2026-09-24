"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: 健康状态报告结构)
- myrm_agent_harness.observability.diagnostics.protocols::DiagnosticProtocol (POS: 诊断接口)
- app.database.models.chat::Chat, Message (POS: 会话与消息 ORM 模型)
- app.database.repositories.uow::UnitOfWork (POS: 数据库工作单元)

[OUTPUT]
- OrphanSessionDiagnostic: 孤儿空壳会话（缺少 Assistant 回复的遗留空会话）健康诊断探针。
- count_orphan_empty_sessions: 统计孤儿空壳会话数量。
- purge_orphan_empty_sessions: 清理遗留孤儿空壳会话。

[POS]
Server 层会话与存储健康诊断探针集合，提供零助手回复会话的生命周期审计与清理。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)
from sqlalchemy import func, select

from app.database.models.chat import Chat, Message
from app.database.repositories.uow import UnitOfWork

logger = logging.getLogger(__name__)


async def count_orphan_empty_sessions(older_than_minutes: int = 15) -> int:
    """Count sessions created before cutoff that have zero assistant messages."""
    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    async with UnitOfWork() as uow:
        sess = uow.session
        if sess is None:
            return 0
        assistant_subq = (
            select(Message.chat_id)
            .where(Message.role == "assistant")
            .distinct()
        )
        stmt = (
            select(func.count(Chat.id))
            .where(
                Chat.created_at < cutoff,
                Chat.deleted_at.is_(None),
                Chat.id.not_in(assistant_subq),
            )
        )
        result = await sess.execute(stmt)
        return int(result.scalar_one_or_none() or 0)


async def purge_orphan_empty_sessions(older_than_minutes: int = 15) -> int:
    """Soft-delete legacy orphan blank sessions lacking assistant messages."""
    from app.services.chat.chat_service import ChatService

    cutoff = datetime.now(UTC) - timedelta(minutes=older_than_minutes)
    orphan_ids: list[str] = []
    async with UnitOfWork() as uow:
        sess = uow.session
        if sess is None:
            return 0
        assistant_subq = (
            select(Message.chat_id)
            .where(Message.role == "assistant")
            .distinct()
        )
        stmt = (
            select(Chat.id)
            .where(
                Chat.created_at < cutoff,
                Chat.deleted_at.is_(None),
                Chat.id.not_in(assistant_subq),
            )
        )
        result = await sess.execute(stmt)
        orphan_ids = [row[0] for row in result.all()]

    if not orphan_ids:
        return 0

    batch_res = await ChatService.batch_delete(orphan_ids)
    deleted_count = batch_res.get("deleted", 0)
    logger.info("Purged %d legacy orphan sessions", deleted_count)
    return deleted_count


class OrphanSessionDiagnostic(DiagnosticProtocol):
    """Diagnostic probe detecting blank sessions lacking assistant responses."""

    async def check_health(self) -> HealthReport:
        try:
            orphan_count = await count_orphan_empty_sessions(older_than_minutes=15)
            meta: dict[str, object] = {
                "orphan_session_count": orphan_count,
                "grace_window_minutes": 15,
            }
            if orphan_count > 0:
                return HealthReport(
                    component_name="OrphanSession",
                    status="pass",
                    code="INFO_ORPHAN_SESSIONS_DETECTED",
                    meta_data=meta,
                    message=f"Found {orphan_count} legacy empty sessions without assistant messages.",
                    detail=(
                        f"Database contains {orphan_count} chat(s) created >15m ago without any assistant responses. "
                        "These can be reclaimed safely via maintenance purge."
                    ),
                    fix_suggestion="Run Doctor maintenance or call purge_orphan_empty_sessions().",
                )
            return HealthReport(
                component_name="OrphanSession",
                status="pass",
                code="OK_NO_ORPHAN_SESSIONS",
                meta_data=meta,
                message="No orphan empty sessions detected in database.",
            )
        except Exception as exc:
            logger.warning("OrphanSession diagnostic check failed: %s", exc)
            return HealthReport(
                component_name="OrphanSession",
                status="pass",
                code="WARN_ORPHAN_SESSION_CHECK_FAILED",
                message="Orphan session health check failed.",
                detail=str(exc),
            )
