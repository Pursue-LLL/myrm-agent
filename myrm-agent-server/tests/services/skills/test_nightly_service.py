"""Tests for the nightly review orchestration against the real DB."""

from __future__ import annotations

import pytest
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import Base, ExperienceLedgerEvent, SystemNotification
from app.platform_utils import get_database_engine
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)
from app.services.skills.nightly_review.service import run_nightly_review


@pytest.fixture(autouse=True)
async def setup_database() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(SystemNotification))
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
async def test_run_opens_watches_and_publishes_digest() -> None:
    for _ in range(3):
        await _record_negative("agent-night")
    report = await run_nightly_review()
    assert report.events_scanned == 3
    assert report.findings_count == 1
    assert report.watches_opened == 1
    assert report.watches_verified == 0
    assert len(report.finding_summaries) == 1

    async with get_session() as db:
        notes = (await db.execute(select(SystemNotification))).scalars().all()
    assert len(notes) == 1
    assert notes[0].title == "夜间体检报告"
    assert notes[0].source == "nightly-review"


@pytest.mark.asyncio
async def test_run_with_clean_day_reports_all_clear() -> None:
    report = await run_nightly_review()
    assert report.events_scanned == 0
    assert report.findings_count == 0
    assert report.watches_opened == 0
    async with get_session() as db:
        notes = (await db.execute(select(SystemNotification))).scalars().all()
    assert len(notes) == 1
    assert "一切正常" in notes[0].message
