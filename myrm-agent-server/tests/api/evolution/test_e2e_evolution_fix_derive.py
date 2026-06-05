import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal, EvolutionType
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow


@pytest.mark.asyncio
async def test_evolution_monitor_service_handles_fix_and_derive():
    """测试 ConfidenceApprovalFlow 对 Fix 和 Derive 的处理，验证 ApprovalRecord 写入。"""

    fix_proposal = EvolutionProposal(
        skill_id="skill_broken_1",
        evolution_type=EvolutionType.FIX,
        original_content="def func():\n    return 1/0",
        proposed_content="def func():\n    return 0",
        diff="--- a\n+++ b\n- return 1/0\n+ return 0",
        score=1.0,
        reasoning="Fixed divide by zero",
        task_context="Error during execution",
        created_at=None,
    )

    derive_proposal = EvolutionProposal(
        skill_id="skill_basic_1",
        evolution_type=EvolutionType.DERIVED,
        original_content="def func():\n    return 1",
        proposed_content="def func(x=1):\n    return x",
        diff="--- a\n+++ b\n- def func():\n-     return 1\n+ def func(x=1):\n+     return x",
        score=0.9,
        reasoning="Derived a more generic function",
        task_context="User asked for x support",
        created_at=None,
    )

    flow = ConfidenceApprovalFlow()

    result_fix = await flow.process_evolution(proposal=fix_proposal)
    assert not result_fix.approved
    assert result_fix.requires_manual_review

    result_derive = await flow.process_evolution(proposal=derive_proposal)
    assert not result_derive.approved
    assert result_derive.requires_manual_review

    async with get_session() as db:
        result = await db.execute(select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution"))
        approvals = result.scalars().all()
        assert len(approvals) >= 2

        types = [a.payload.get("evolution_type") for a in approvals if isinstance(a.payload, dict)]
        assert "fix" in types
        assert "derived" in types

        for a in approvals:
            await db.delete(a)
        await db.commit()
