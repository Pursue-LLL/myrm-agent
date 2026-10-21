"""Tests for regression watches against the real ledger DB."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)
from app.services.skills.nightly_review.acceptance import (
    WATCH_OUTCOME_OPEN,
    WATCH_OUTCOME_VERIFIED,
    build_watch_id,
    open_watch,
    verify_watch,
)


@pytest.fixture(autouse=True)
async def setup_database() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.commit()


async def _record_negative(entity_id: str) -> None:
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_REJECTED.value,
            entity_type=ExperienceEntityType.REVIEW.value,
            entity_id=entity_id,
            lineage_id=f"lineage-{entity_id}",
            summary="rejected",
            namespace="default",
        )
    )


@pytest.mark.asyncio
async def test_open_watch_persists_pending_record() -> None:
    watch = await open_watch(entity_type="review", entity_id="agent-a", summary="watch it")
    assert watch.watch_id == build_watch_id("review", "agent-a", watch.opened_at)
    async with get_session() as db:
        rows = (
            (await db.execute(select(ExperienceLedgerEvent).where(ExperienceLedgerEvent.entity_id == watch.watch_id)))
            .scalars()
            .all()
        )
    assert len(rows) == 1
    assert rows[0].outcome == WATCH_OUTCOME_OPEN


@pytest.mark.asyncio
async def test_verify_false_when_window_not_elapsed() -> None:
    watch = await open_watch(entity_type="review", entity_id="agent-a", summary="watch it")
    assert await verify_watch(watch) is False


@pytest.mark.asyncio
async def test_verify_false_on_recurrence() -> None:
    opened_at = datetime.now(UTC) - timedelta(hours=30)
    watch = await open_watch(entity_type="review", entity_id="agent-a", summary="watch it", opened_at=opened_at)
    await _record_negative("agent-a")
    assert await verify_watch(watch) is False


@pytest.mark.asyncio
async def test_verify_true_when_clean_and_close_verified_event() -> None:
    opened_at = datetime.now(UTC) - timedelta(hours=30)
    watch = await open_watch(entity_type="review", entity_id="agent-b", summary="watch it", opened_at=opened_at)
    assert await verify_watch(watch) is True
    async with get_session() as db:
        rows = (
            (
                await db.execute(
                    select(ExperienceLedgerEvent).where(
                        ExperienceLedgerEvent.entity_id == watch.watch_id,
                        ExperienceLedgerEvent.outcome == WATCH_OUTCOME_VERIFIED,
                    )
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1
