"""
Fission Repository — data access layer for FissionTaskRecord.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.fission import FissionTaskRecord


class FissionRepository:
    """Repository for Fission Task Records."""

    @staticmethod
    async def get_fission_record(db: AsyncSession, fission_id: str) -> FissionTaskRecord | None:
        result = await db.execute(
            select(FissionTaskRecord).where(FissionTaskRecord.fission_id == fission_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_or_update_record(
        db: AsyncSession,
        fission_id: str,
        chat_id: str,
        agent_id: str,
        nodes: list[dict[str, object]],
        total_cost_usd: float = 0.0,
    ) -> FissionTaskRecord:
        record = await FissionRepository.get_fission_record(db, fission_id)
        if record:
            # Reassign list to trigger SQLAlchemy JSON dirty tracking
            record.nodes = list(nodes)
            record.total_cost_usd = total_cost_usd
        else:
            record = FissionTaskRecord(
                fission_id=fission_id,
                chat_id=chat_id,
                agent_id=agent_id,
                nodes=list(nodes),
                total_cost_usd=total_cost_usd,
            )
            db.add(record)

        await db.flush()
        await db.refresh(record)
        return record
