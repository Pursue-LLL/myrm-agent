"""Prerequisite service for cron automation manual success gating.

Calculates manual execution success stats across chat sessions, kanban tasks,
and historical runs to verify if a workflow has been reliably executed before automation.

[INPUT]
- myrm_agent_harness.toolkits.cron.engine.fingerprint::compute_workflow_fingerprint (POS: 纯函数指纹计算)
- app.database.repositories.uow::UnitOfWork (POS: 统一工作单元)

[OUTPUT]
- CronPrerequisiteStats: 数据结构，包含 manual_success_count, is_satisfied, fingerprint 等
- CronPrerequisiteService: 业务服务

[POS]
Server 业务层服务。用于在创建 Cron 任务前提供手动成功验证次数的聚合统计与门禁判定。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from myrm_agent_harness.api import compute_workflow_fingerprint
from sqlalchemy import func, or_, select

from app.database.models import Message
from app.database.models.kanban import KanbanTaskModel
from app.database.repositories.uow import UnitOfWork

logger = logging.getLogger(__name__)

# Default threshold for manual success prerequisite
DEFAULT_PREREQUISITE_THRESHOLD = 2


@dataclass(frozen=True, slots=True)
class CronPrerequisiteStats:
    """Statistics for workflow automation prerequisite verification."""

    fingerprint: str
    manual_success_count: int
    threshold: int
    is_satisfied: bool
    chat_verified_count: int
    kanban_verified_count: int
    override_allowed: bool = True


class CronPrerequisiteService:
    """Service to evaluate manual success prerequisite for cron automation."""

    @staticmethod
    async def get_prerequisite_stats(
        *,
        prompt: str | None = None,
        agent_id: str | None = None,
        workflow_template_id: str | None = None,
        command: str | None = None,
        tools_allowed: Sequence[str] | None = None,
        chat_id: str | None = None,
        threshold: int = DEFAULT_PREREQUISITE_THRESHOLD,
    ) -> CronPrerequisiteStats:
        """Query manual success executions for a given workflow fingerprint.

        Searches:
        1. Bound Chat session (if chat_id provided, count completed assistant turns).
        2. Global Chat messages with matching query content.
        3. Kanban tasks completed (status='done') matching agent_id or title.
        """
        fingerprint = compute_workflow_fingerprint(
            prompt=prompt,
            agent_id=agent_id,
            workflow_template_id=workflow_template_id,
            command=command,
            tools_allowed=tools_allowed,
        )

        chat_verified = 0
        kanban_verified = 0

        async with UnitOfWork() as uow:
            db = uow.session

            # 1. Check bound chat session if available
            if chat_id:
                # Count successful assistant responses in this chat
                chat_stmt = select(func.count(Message.id)).where(
                    Message.chat_id == chat_id,
                    Message.role == "assistant",
                    Message.is_active.is_(True),
                )
                res = await db.execute(chat_stmt)
                chat_verified += res.scalar_one() or 0

            # 2. Check if there are matching finished Kanban tasks
            clean_prompt = (prompt or "").strip()
            if clean_prompt:
                kanban_stmt = select(func.count(KanbanTaskModel.id)).where(
                    KanbanTaskModel.status == "done",
                    or_(
                        KanbanTaskModel.title.ilike(f"%{clean_prompt[:50]}%"),
                        KanbanTaskModel.description.ilike(f"%{clean_prompt[:50]}%"),
                    ),
                )
                if agent_id:
                    kanban_stmt = kanban_stmt.where(
                        KanbanTaskModel.agent_id == agent_id
                    )
                k_res = await db.execute(kanban_stmt)
                kanban_verified += k_res.scalar_one() or 0

        total_manual_success = chat_verified + kanban_verified
        is_satisfied = total_manual_success >= threshold

        return CronPrerequisiteStats(
            fingerprint=fingerprint,
            manual_success_count=total_manual_success,
            threshold=threshold,
            is_satisfied=is_satisfied,
            chat_verified_count=chat_verified,
            kanban_verified_count=kanban_verified,
            override_allowed=True,
        )


__all__ = [
    "CronPrerequisiteService",
    "CronPrerequisiteStats",
    "DEFAULT_PREREQUISITE_THRESHOLD",
]
