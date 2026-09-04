"""Memory conflict tracking and human adjudication service.

[INPUT]
app.database.models.memory::MemoryConflictModel (POS: 记忆冲突待决数据模型)
myrm_agent_harness.toolkits.memory::MemoryManager (POS: 内存核心管理器)
myrm_agent_harness.toolkits.memory.strategies.merger::ConfidenceEvolutionEngine (POS: 置信度演进与自愈引擎)
myrm_agent_harness.toolkits.memory.strategies.merger::ConflictItem (POS: 冲突 DTO)

[OUTPUT]
MemoryConflictService: 冲突管理与仲裁业务服务

[POS]
记忆冲突服务层。管理未决记忆矛盾的暂存、人类仲裁（采纳/保留/共存）以及14天半衰期自然平滑自愈。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from myrm_agent_harness.api import (
    ConfidenceEvolutionEngine,
    ConflictItem,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import MemoryConflictModel


class MemoryConflictService:
    """Handles memory conflict storage, temporal self-healing, and human arbitration."""

    def __init__(self, db: AsyncSession, manager: MemoryManager) -> None:
        self._db = db
        self._manager = manager

    async def record_conflict(
        self,
        existing_memory_id: str,
        existing_content: str,
        candidate_content: str,
        candidate_memory_id: str | None = None,
        facet: str | None = None,
    ) -> MemoryConflictModel:
        """Record or update a pending contradiction between existing memory and a new candidate fact."""
        stmt = (
            select(MemoryConflictModel)
            .where(
                MemoryConflictModel.existing_memory_id == existing_memory_id,
                MemoryConflictModel.status == "pending",
            )
            .order_by(MemoryConflictModel.detected_at.desc())
            .limit(1)
        )
        res = await self._db.execute(stmt)
        existing_conflict = res.scalar_one_or_none()

        if existing_conflict:
            existing_conflict.activation_count += 1
            if candidate_memory_id:
                existing_conflict.candidate_memory_id = candidate_memory_id

            conflict_dto = ConflictItem(
                conflict_id=existing_conflict.id,
                existing_memory_id=existing_conflict.existing_memory_id,
                candidate_content=existing_conflict.candidate_content,
                existing_content=existing_conflict.existing_content,
                facet=existing_conflict.facet,
                detected_at=existing_conflict.detected_at,
                activation_count=existing_conflict.activation_count,
            )

            # Check for 14-day temporal self-healing (>= 3 confirmations without contradiction)
            if ConfidenceEvolutionEngine.check_temporal_reconciliation(conflict_dto):
                await self.resolve_conflict(existing_conflict.id, action="keep_new", is_automated=True)

            await self._db.commit()
            await self._db.refresh(existing_conflict)
            return existing_conflict

        new_conflict = MemoryConflictModel(
            id=str(uuid4()),
            existing_memory_id=existing_memory_id,
            candidate_memory_id=candidate_memory_id,
            candidate_content=candidate_content,
            existing_content=existing_content,
            facet=facet,
            status="pending",
            activation_count=1,
            detected_at=datetime.now(UTC),
        )
        self._db.add(new_conflict)
        await self._db.commit()
        await self._db.refresh(new_conflict)
        return new_conflict

    async def list_pending_conflicts(self, limit: int = 50) -> list[MemoryConflictModel]:
        """Fetch all active conflicts awaiting human review or temporal resolution."""
        stmt = (
            select(MemoryConflictModel)
            .where(MemoryConflictModel.status == "pending")
            .order_by(MemoryConflictModel.detected_at.desc())
            .limit(limit)
        )
        res = await self._db.execute(stmt)
        return list(res.scalars().all())

    async def resolve_conflict(
        self,
        conflict_id: str,
        action: Literal["keep_new", "keep_old", "coexist"],
        is_automated: bool = False,
    ) -> bool:
        """Arbitrate a memory conflict with explicit human decision or temporal auto-reconciliation."""
        conflict = await self._db.get(MemoryConflictModel, conflict_id)
        if not conflict or conflict.status != "pending":
            return False

        now = datetime.now(UTC)
        conflict.resolved_at = now
        conflict.resolution_action = f"{action}_auto" if is_automated else action
        conflict.status = "resolved"

        existing_id = conflict.existing_memory_id
        candidate_id = conflict.candidate_memory_id

        if action == "keep_new":
            # Demote/archive old memory, promote candidate
            try:
                await self._manager.update_memory(existing_id, importance=0.01)
            except Exception:
                pass

            if candidate_id:
                try:
                    await self._manager.update_memory(candidate_id, confidence=0.95)
                except Exception:
                    pass
            else:
                await self._manager.add_memory(
                    conflict.candidate_content,
                    memory_type=MemoryType.SEMANTIC,
                    confidence=0.95,
                )

        elif action == "keep_old":
            # Lock existing memory against future overwrite; discard candidate
            try:
                await self._manager.update_memory(existing_id, confidence=0.95, is_user_locked=True)
            except Exception:
                pass

            if candidate_id:
                try:
                    await self._manager.delete_memory(candidate_id)
                except Exception:
                    pass

        elif action == "coexist":
            # Both statements are retained with standard active confidence
            try:
                await self._manager.update_memory(existing_id, confidence=0.85)
            except Exception:
                pass
            if candidate_id:
                try:
                    await self._manager.update_memory(candidate_id, confidence=0.85)
                except Exception:
                    pass

        await self._db.commit()
        return True
