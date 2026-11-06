"""[INPUT]
- app.database.models / harness profile types (POS: ORM + domain types)

[OUTPUT]
- ReadsMixin

[POS]
AgentRepository mixin: single profile, paginated listing and counting.
"""

from __future__ import annotations

from myrm_agent_harness.backends.profiles.types import AgentProfile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Agent

from .mapping import MappingMixin


class ReadsMixin:
    @staticmethod
    async def get_profile(db: AsyncSession, agent_id: str) -> AgentProfile | None:
        result = await db.execute(select(Agent).where(Agent.id == agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            return None
        return MappingMixin._agent_to_profile(agent)

    @staticmethod
    async def list_profiles(
        db: AsyncSession,
        *,
        offset: int = 0,
        limit: int | None = None,
        exclude_ids: list[str] | None = None,
    ) -> list[AgentProfile]:
        stmt = select(Agent)
        if exclude_ids:
            stmt = stmt.where(Agent.id.notin_(exclude_ids))
        # Deterministic newest-first order: single-page consumers (listAgents(1, N))
        # must always see freshly created agents, and DB-default ordering is
        # undefined, which silently drops new agents once rows exceed one page.
        stmt = stmt.order_by(Agent.created_at.desc(), Agent.id)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        agents = result.scalars().all()
        return [MappingMixin._agent_to_profile(agent) for agent in agents]

    @staticmethod
    async def count_profiles(
        db: AsyncSession,
        *,
        exclude_ids: list[str] | None = None,
    ) -> int:
        from sqlalchemy import func

        stmt = select(func.count()).select_from(Agent)
        if exclude_ids:
            stmt = stmt.where(Agent.id.notin_(exclude_ids))
        result = await db.execute(stmt)
        return result.scalar_one()
