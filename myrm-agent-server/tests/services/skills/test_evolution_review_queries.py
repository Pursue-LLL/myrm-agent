"""SQL pushdown tests for evolution review list/count queries."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import delete

from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.platform_utils import get_database_engine
from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.evolution_reviews import (
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    count_evolution_review_records,
    create_evolution_review_record,
    list_evolution_review_records,
)


@pytest.fixture(autouse=True)
async def ensure_tables() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


async def _create_record(
    *,
    growth_status: EvolutionGrowthStatus = EvolutionGrowthStatus.PENDING_REVIEW,
    approval_status: str = "PENDING",
) -> EvolutionReviewRecord:
    return await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id=f"skill_{uuid.uuid4().hex[:8]}",
        skill_name="test_skill",
        skill_path=f"/tmp/test_skill_{uuid.uuid4().hex}.md",
        evolution_type="fix",
        reason="SQL pushdown test",
        original_content="def foo(): pass",
        evolved_content="def foo(): return 1",
        confidence=0.8,
        test_passed=True,
        task_context="evolution review query test",
        growth_status=growth_status,
        approval_status=approval_status,
    )


@pytest.mark.asyncio
async def test_list_evolution_review_records_respects_sql_limit() -> None:
    for _ in range(4):
        await _create_record()

    records = await list_evolution_review_records(limit=2, pending_only=False)
    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_evolution_review_records_pending_only_filters_in_sql() -> None:
    pending = await _create_record(growth_status=EvolutionGrowthStatus.PENDING_REVIEW)
    apply_failed = await _create_record(growth_status=EvolutionGrowthStatus.APPLY_FAILED)
    await _create_record(
        growth_status=EvolutionGrowthStatus.APPROVED,
        approval_status="APPROVED",
    )
    await _create_record(
        growth_status=EvolutionGrowthStatus.REJECTED,
        approval_status="REJECTED",
    )

    pending_records = await list_evolution_review_records(limit=10, pending_only=True)
    pending_ids = {record.id for record in pending_records}

    assert pending_ids == {pending.id, apply_failed.id}
    assert all(
        record.status in {EvolutionGrowthStatus.PENDING_REVIEW, EvolutionGrowthStatus.APPLY_FAILED}
        for record in pending_records
    )


@pytest.mark.asyncio
async def test_count_evolution_review_records_pending_only_uses_sql() -> None:
    await _create_record(growth_status=EvolutionGrowthStatus.PENDING_REVIEW)
    await _create_record(growth_status=EvolutionGrowthStatus.APPLY_FAILED)
    await _create_record(
        growth_status=EvolutionGrowthStatus.REJECTED,
        approval_status="REJECTED",
    )

    assert await count_evolution_review_records(pending_only=True) == 2
    assert await count_evolution_review_records(pending_only=False) == 3


@pytest.mark.asyncio
async def test_pending_only_includes_legacy_records_without_growth_status() -> None:
    record = await ApprovalRegistry.create_approval(
        agent_id="test-agent",
        action_type="evolution",
        payload={
            "schema_version": 1,
            "skill_id": "legacy-skill",
            "skill_name": "legacy",
            "skill_path": "/tmp/legacy.md",
            "evolution_type": "fix",
            "reason": "legacy record",
            "original_content": "old",
            "evolved_content": "new",
            "confidence": 0.5,
            "test_passed": True,
        },
        reason="legacy record",
        severity="warning",
        status="PENDING",
    )

    pending_records = await list_evolution_review_records(limit=10, pending_only=True)
    pending_ids = {item.id for item in pending_records}

    assert record.id in pending_ids
    assert await count_evolution_review_records(pending_only=True) >= 1
