import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal, EvolutionType
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord, Base, ExperienceLedgerEvent
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="evolution")
from app.platform_utils import get_database_engine
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.skills.evolution_reviews import EvolutionReviewRecord, create_evolution_review_record

_EVOLVED_SKILL_MD = "---\nname: test-skill\ndescription: Fixes the skill.\n---\n\n# Test skill\n"


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
        evolved_content=_EVOLVED_SKILL_MD,
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
        assert file_obj.read() == _EVOLVED_SKILL_MD


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
        evolved_content=_EVOLVED_SKILL_MD,
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
    assert "cannot be loaded" not in body["apply_error"]
    assert body["reason_code"] == "apply_failed"
    assert body["remediation"] is not None

    async with get_session() as db:
        approval_record = await db.get(ApprovalRecord, record.id)
        assert approval_record is not None
        assert approval_record.status == "APPROVED"
        assert isinstance(approval_record.payload, dict)
        assert approval_record.payload["growth_status"] == "APPLY_FAILED"
        assert approval_record.payload["apply_status"] == "FAILED"


@pytest.mark.asyncio
async def test_approve_pending_evolution_refuses_content_the_skill_loader_would_skip(
    async_client: AsyncClient, tmp_path: Path
) -> None:
    skill_file = tmp_path / "unloadable-skill" / "SKILL.md"
    record = await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id="unloadable_skill_123",
        skill_name="unloadable-skill",
        skill_path=str(skill_file),
        evolution_type="fix",
        reason="The drafted file lost its frontmatter",
        original_content="# Unloadable skill\n",
        evolved_content="# Unloadable skill, fixed\n",
        confidence=0.9,
        test_passed=True,
        task_context="unloadable content regression",
    )

    response = await async_client.post(f"/api/v1/evolution/pending/{record.id}/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "apply_failed"
    assert "cannot be loaded" in body["apply_error"]
    assert body["reason_code"] == "skill_md_unloadable"
    assert "revise the proposal" in body["remediation"]
    assert not skill_file.parent.exists()


@pytest.mark.asyncio
async def test_approve_pending_evolution_refuses_a_skill_edited_since_the_proposal_was_created(
    async_client: AsyncClient, tmp_path: Path
) -> None:
    skill_file = tmp_path / "edited-skill" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text("---\nname: edited-skill\ndescription: As proposed against.\n---\n", encoding="utf-8")
    record = await create_evolution_review_record(
        agent_id="test-agent",
        chat_id=None,
        proposal_skill_id="edited_skill_123",
        skill_name="edited-skill",
        skill_path=str(skill_file),
        evolution_type="fix",
        reason="The proposal was built before the user edited the skill",
        original_content="---\nname: edited-skill\ndescription: As proposed against.\n---\n",
        evolved_content=_EVOLVED_SKILL_MD,
        confidence=0.9,
        test_passed=True,
        task_context="stale base regression",
    )
    edited = "---\nname: edited-skill\ndescription: Edited by the user since.\n---\n"
    skill_file.write_text(edited, encoding="utf-8")

    response = await async_client.post(f"/api/v1/evolution/pending/{record.id}/approve")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "apply_failed"
    assert body["reason_code"] == "stale_base"
    assert "reject the proposal" in body["remediation"]
    assert skill_file.read_text(encoding="utf-8") == edited


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
