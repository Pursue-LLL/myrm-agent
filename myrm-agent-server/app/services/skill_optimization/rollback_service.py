"""
[INPUT]
- app.database.models.BatchSnapshot (POS: 批次前快照行)
[OUTPUT]
- RollbackService (写入 rollback-eligible 批次的前快照行；恢复由 app.services.skills.mutation_batch_service 执行)
[POS]
batch_snapshots 的写入口：skill_manage 批次与 market replace 在变更前落库快照，供 /mutations/{batch_id}/rollback 撤销。
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import BatchSnapshot


class RollbackService:
    """Persists pre-mutation snapshots that a later rollback restores from."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert_mutation_batch_snapshot(
        self,
        batch_id: str,
        skill_id: str,
        skill_content: str,
        metadata: dict[str, object],
        *,
        commit: bool = True,
    ) -> None:
        """Persist a pre-mutation snapshot for skill_manage batches."""
        self.session.add(
            BatchSnapshot(
                snapshot_id=str(uuid.uuid4()),
                batch_id=batch_id,
                skill_id=skill_id,
                skill_content_before=skill_content,
                skill_version_before=0,
                skill_metadata=metadata,
            )
        )
        if commit:
            await self.session.commit()
