from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
    SkillLineage,
    SkillMetrics,
    SkillRecord,
)
from sqlalchemy import delete, select

from app.api.memory.utils import get_crud_memory_manager, get_memory_manager
from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent, PendingMigration
from app.main import app
from app.platform_utils import get_database_engine
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow


class FakeMemoryManager:
    approval_required = True

    async def approve(self, pending_id: str) -> None:
        return None

    async def reject(self, pending_id: str) -> None:
        return None


class FakeCrudMemoryManager:
    def __init__(self) -> None:
        self.import_memories = AsyncMock(return_value={"semantic": 1})


@pytest.fixture(autouse=True)
async def ensure_tables() -> None:
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.fixture(autouse=True)
async def cleanup_rows() -> None:
    yield
    async with get_session() as db:
        await db.execute(delete(ExperienceLedgerEvent))
        await db.execute(delete(PendingMigration))
        await db.execute(delete(ApprovalRecord))
        await db.commit()


@pytest.fixture
async def async_client():
    fake_crud = FakeCrudMemoryManager()
    app.dependency_overrides[get_memory_manager] = lambda: FakeMemoryManager()
    app.dependency_overrides[get_crud_memory_manager] = lambda: fake_crud
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client, fake_crud
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_submit_migration_creates_ledger_event(async_client) -> None:
    client, _ = async_client
    response = await client.post(
        "/api/v1/migrations/memory/submit",
        json={
            "source": "hermes",
            "version": 1,
            "skip_duplicates": True,
            "data": {"semantic": [{"content": "Ledger should capture migration lineage."}]},
        },
    )
    assert response.status_code == 200
    migration_id = response.json()["migration_id"]

    ledger_response = await client.get("/api/v1/experience-ledger/events?lineage_id=migration:" + migration_id)
    assert ledger_response.status_code == 200
    body = ledger_response.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "migration.submitted"


@pytest.mark.asyncio
async def test_review_approve_migration_writes_domain_and_review_events(async_client) -> None:
    client, fake_crud = async_client
    async with get_session() as db:
        pending = PendingMigration(
            id=uuid.uuid4().hex,
            source="openclaw",
            migration_type="memory_import",
            summary="Pending migration from openclaw (1 items; semantic:1)",
            total_items=1,
            item_counts={"semantic": 1},
            payload={"version": 1, "skip_duplicates": True, "data": {"semantic": [{"content": "x"}]}},
            status="pending",
        )
        db.add(pending)
        await db.commit()

    response = await client.post(f"/api/v1/reviews/migration/{pending.id}/approve")
    assert response.status_code == 200
    fake_crud.import_memories.assert_awaited_once()

    async with get_session() as db:
        result = await db.execute(select(ExperienceLedgerEvent).order_by(ExperienceLedgerEvent.created_at.asc()))
        events = list(result.scalars().all())

    event_types = [event.event_type for event in events]
    assert "migration.approved" in event_types
    assert "review.approved" in event_types


@pytest.mark.asyncio
async def test_low_confidence_evolution_creates_pending_ledger_event() -> None:
    flow = ConfidenceApprovalFlow(auto_approve_threshold=0.9)
    SkillRecord(
        skill_id="ledger_skill",
        name="ledger-skill",
        description="",
        content="def foo(): return 2",
        path="/tmp/ledger_skill.md",
        lineage=SkillLineage(evolution_type=EvolutionType.FIX, change_summary="Fix with ledger"),
        metrics=SkillMetrics(),
    )

    from datetime import datetime

    mock_proposal = EvolutionProposal(
        skill_id="ledger_skill",
        evolution_type=EvolutionType.FIX,
        original_content="def foo(): pass",
        proposed_content="def foo(): pass\n# fixed",
        diff="dummy diff",
        score=0.7,
        reasoning="fix bug",
        task_context="ledger validation",
        created_at=datetime.now(),
    )
    result = await flow.process_evolution(
        proposal=mock_proposal,
    )

    assert result.requires_manual_review is True

    async with get_session() as db:
        approval_result = await db.execute(
            select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution")
        )
        approvals = list(approval_result.scalars().all())
        pending = next(
            (
                record
                for record in approvals
                if isinstance(record.payload, dict) and record.payload.get("skill_id") == "ledger_skill"
            ),
            None,
        )
        assert pending is not None

        ledger_result = await db.execute(
            select(ExperienceLedgerEvent).where(
                ExperienceLedgerEvent.entity_id == pending.id,
            )
        )
        event = ledger_result.scalars().first()
        assert event is not None
        assert event.event_type == "evolution.pending"
