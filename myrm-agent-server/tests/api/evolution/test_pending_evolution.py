import os
import uuid
from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal, EvolutionType
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from app.main import app
from app.platform_utils import get_database_engine
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.skills.evolution_reviews import EvolutionReviewRecord, create_evolution_review_record


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


@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
async def sample_pending_evolution() -> EvolutionReviewRecord:
    skill_path = f"/tmp/test_skill_{uuid.uuid4().hex}.md"
    record = await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id="test_skill_123",
        skill_name="test_skill",
        skill_path=skill_path,
        evolution_type="fix",
        reason="Fix a bug",
        original_content="def foo(): pass",
        evolved_content="def foo(): return 1",
        confidence=0.8,
        test_passed=True,
        task_context="pending evolution regression",
    )
    yield record
    if os.path.exists(skill_path):
        os.remove(skill_path)
    bak_path = f"{skill_path}.bak"
    if os.path.exists(bak_path):
        os.remove(bak_path)


@pytest.mark.asyncio
async def test_get_pending_evolutions(async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord) -> None:
    response = await async_client.get("/api/v1/evolution/pending")
    assert response.status_code == 200
    data = response.json()

    item_ids = [item["id"] for item in data["items"]]
    assert sample_pending_evolution.id in item_ids

    item = next(item for item in data["items"] if item["id"] == sample_pending_evolution.id)
    assert item["skill_id"] == "test_skill_123"
    assert item["status"] == "PENDING_REVIEW"
    assert item["approval_status"] == "PENDING"
    assert item["apply_status"] == "NOT_APPLIED"


@pytest.mark.asyncio
async def test_approve_pending_evolution(async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord) -> None:
    response = await async_client.post(f"/api/v1/evolution/pending/{sample_pending_evolution.id}/approve")
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["apply_status"] == "APPLIED"

    async with get_session() as db:
        record = await db.get(ApprovalRecord, sample_pending_evolution.id)
        assert record is not None
        assert record.status == "APPROVED"
        assert isinstance(record.payload, dict)
        assert record.payload["growth_status"] == "APPROVED"
        assert record.payload["apply_status"] == "APPLIED"

    with open(sample_pending_evolution.skill_path, "r", encoding="utf-8") as file_obj:
        assert file_obj.read() == "def foo(): return 1"


@pytest.mark.asyncio
async def test_approve_pending_evolution_returns_apply_failed_state(async_client: AsyncClient) -> None:
    record = await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id="broken_skill_123",
        skill_name="broken_skill",
        skill_path="/dev/null/broken_skill.md",
        evolution_type="fix",
        reason="Apply should fail because the parent path is not a directory",
        original_content="def foo(): pass",
        evolved_content="def foo(): return 1",
        confidence=0.9,
        test_passed=True,
        task_context="apply failure regression",
    )

    response = await async_client.post(f"/api/v1/evolution/pending/{record.id}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "apply_failed"
    assert body["apply_status"] == "FAILED"
    assert body["apply_error"] is not None
    assert body["remediation"] is not None

    async with get_session() as db:
        approval_record = await db.get(ApprovalRecord, record.id)
        assert approval_record is not None
        assert approval_record.status == "APPROVED"
        assert isinstance(approval_record.payload, dict)
        assert approval_record.payload["growth_status"] == "APPLY_FAILED"
        assert approval_record.payload["apply_status"] == "FAILED"


@pytest.mark.asyncio
async def test_reject_pending_evolution(async_client: AsyncClient, sample_pending_evolution: EvolutionReviewRecord) -> None:
    response = await async_client.post(f"/api/v1/evolution/pending/{sample_pending_evolution.id}/reject")
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"

    async with get_session() as db:
        record = await db.get(ApprovalRecord, sample_pending_evolution.id)
        assert record is not None
        assert record.status == "REJECTED"
        assert isinstance(record.payload, dict)
        assert record.payload["growth_status"] == "REJECTED"


@pytest.mark.asyncio
async def test_confidence_approval_flow_creates_pending() -> None:
    flow = ConfidenceApprovalFlow(auto_approve_threshold=0.9)

    mock_proposal = EvolutionProposal(
        skill_id="test_skill_456",
        evolution_type=EvolutionType.FIX,
        original_content="def foo(): pass",
        proposed_content="def foo(): pass\n# fixed",
        diff="dummy diff",
        score=0.8,
        reasoning="fix bug",
        task_context="",
        created_at=datetime.now(),
    )
    result = await flow.process_evolution(proposal=mock_proposal)

    assert not result.approved
    assert result.requires_manual_review

    async with get_session() as db:
        result_rows = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        records = list(result_rows.scalars().all())

    record = next(
        (item for item in records if isinstance(item.payload, dict) and item.payload.get("skill_id") == "test_skill_456"),
        None,
    )
    assert record is not None
    assert record.status == "PENDING"
    assert isinstance(record.payload, dict)
    assert record.payload["confidence"] == 0.8
    assert record.payload["growth_status"] == "PENDING_REVIEW"
