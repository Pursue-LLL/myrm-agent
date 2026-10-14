"""Fixtures for the risk-rule tests: a real SQLite database and a detection engine loaded from it."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import RiskHit, RiskRule
from app.services.risk.detection import RiskDetectionService
from app.services.risk.rule_service import RiskRuleService

EngineBuilder = Callable[..., Awaitable[RiskDetectionService]]


@pytest.fixture()
async def session_factory(tmp_path: Path) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'risk.db'}", connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(cast(Table, RiskRule.__table__).create)
        await conn.run_sync(cast(Table, RiskHit.__table__).create)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture()
def build_engine(session_factory: async_sessionmaker[AsyncSession]) -> EngineBuilder:
    """Load a detection engine from the stored rules: the seeded built-ins (all of them when *enable_all*) or none."""

    async def build(*, seed_builtins: bool = True, enable_all: bool = False) -> RiskDetectionService:
        service = RiskDetectionService()
        rules = RiskRuleService()
        async with session_factory() as db:
            if seed_builtins:
                await rules.seed_builtin_rules(db)
                if enable_all:
                    await rules.batch_toggle(db, [rule.rule_id for rule in await rules.list_rules(db)], True)
                await db.commit()
            await service.reload(db)
        return service

    return build
