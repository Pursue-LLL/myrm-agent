import os
from pathlib import Path

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionProposal,
    EvolutionType,
    SkillLineage,
    SkillMetrics,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow


@pytest.mark.asyncio
async def test_confidence_approval_flow_reject_creates_constraint():
    """测试 Reject 提案后，原因被记录到 SkillStore Constraints 供下次生成吸收。"""
    mock_proposal = EvolutionProposal(
        skill_id="skill_reject_test",
        evolution_type=EvolutionType.FIX,
        original_content="def hello(): return 1",
        proposed_content="def hello(): return '1'",
        diff="dummy",
        score=0.9,
        reasoning="Type change",
        task_context="Error during execution",
        created_at=None,
    )

    flow = ConfidenceApprovalFlow()
    result = await flow.process_evolution(proposal=mock_proposal)
    assert result.requires_manual_review

    async with get_session() as db:
        result_db = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        approval = result_db.scalars().first()
    assert approval is not None

    data_dir = os.getenv("MYRM_DATA_DIR", str(Path.home() / ".myrm"))
    store = SkillStore(db_path=Path(data_dir) / "skills.db")

    dummy = SkillRecord(
        skill_id="skill_reject_test",
        name="x",
        description="x",
        content="x",
        path="x",
        lineage=SkillLineage(evolution_type=EvolutionType.FIX),
        metrics=SkillMetrics(),
    )
    try:
        await store.save_skill(dummy)
    finally:
        store.close()

    from app.api.skills.evolution import reject_pending_evolution_record

    await reject_pending_evolution_record(evolution_id=approval.id, reason="I don't want strings, I want integers in production")

    async with get_session() as db:
        record = await db.get(ApprovalRecord, approval.id)
        assert record is not None
        assert record.status == "REJECTED"

    store = SkillStore(db_path=Path(data_dir) / "skills.db")
    try:
        constraints = store.get_evolution_constraints("skill_reject_test")
    finally:
        store.close()

    assert "I don't want strings, I want integers in production" in constraints

    async with get_session() as db:
        await db.delete(record)
        await db.commit()
