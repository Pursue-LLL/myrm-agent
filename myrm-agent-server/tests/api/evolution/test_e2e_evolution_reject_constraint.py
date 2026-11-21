import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from sqlalchemy import select

from app.api.skills.evolution import reject_pending_evolution_record
from app.core.skills.store.evolution_store import (
    get_evolution_skill_store,
    reset_evolution_skill_store,
)
from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow


async def _pending_approval(skill_id: str) -> ApprovalRecord:
    """Put a proposal for ``skill_id`` through the approval flow and return the review record it queued."""
    proposal = EvolutionProposal(
        skill_id=skill_id,
        evolution_type=EvolutionType.FIX,
        original_content="def hello(): return 1",
        proposed_content="def hello(): return '1'",
        diff="dummy",
        score=0.9,
        reasoning="Type change",
        task_context="Error during execution",
        created_at=None,
    )
    result = await ConfidenceApprovalFlow().process_evolution(proposal=proposal)
    assert result.requires_manual_review

    async with get_session() as db:
        queued = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
    approval = queued.scalars().first()
    assert approval is not None
    return approval


@pytest.mark.asyncio
async def test_confidence_approval_flow_reject_creates_constraint():
    """测试 Reject 提案后，原因被记录到 SkillStore Constraints 供下次生成吸收。"""
    approval = await _pending_approval("skill_reject_test")

    store = get_evolution_skill_store()

    dummy = SkillRecord(
        skill_id="skill_reject_test",
        name="x",
        description="x",
        content="x",
        path="x",
        lineage=SkillLineage(evolution_type=EvolutionType.FIX),
    )
    try:
        await store.save_skill(dummy)
    finally:
        reset_evolution_skill_store()

    await reject_pending_evolution_record(evolution_id=approval.id, reason="I don't want strings, I want integers in production")

    async with get_session() as db:
        record = await db.get(ApprovalRecord, approval.id)
        assert record is not None
        assert record.status == "REJECTED"

    store = get_evolution_skill_store()
    try:
        constraints = store.get_evolution_constraints("skill_reject_test")
    finally:
        reset_evolution_skill_store()

    assert "I don't want strings, I want integers in production" in constraints

    async with get_session() as db:
        await db.delete(record)
        await db.commit()


@pytest.mark.asyncio
async def test_rejecting_with_a_reason_succeeds_for_a_skill_without_a_store_row():
    """A proposal may name a skill the evolution store holds no row for; its rejection and reason are still recorded."""
    reason = "Keep the existing headings"
    approval = await _pending_approval("skill_without_a_row")
    try:
        review = await reject_pending_evolution_record(evolution_id=approval.id, reason=reason)

        assert review.status == "REJECTED"
        assert review.remediation == reason
        async with get_session() as db:
            record = await db.get(ApprovalRecord, approval.id)
        assert record is not None
        assert record.status == "REJECTED"
        assert get_evolution_skill_store().get_evolution_constraints("skill_without_a_row") == []
    finally:
        reset_evolution_skill_store()
