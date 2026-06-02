import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal, EvolutionType
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow


@pytest.mark.asyncio
async def test_confidence_approval_flow_ast_block():
    """测试 AST Syntax 验证不通过时，Score 被置为 0.0，且 test_passed=False 的阻断拦截流程。"""

    failed_proposal = EvolutionProposal(
        skill_id="skill_syntax_error",
        evolution_type=EvolutionType.FIX,
        original_content="def good(): pass",
        proposed_content="```python\ndef bad(:\n    return 1\n```",
        diff="dummy",
        score=0.0,
        reasoning="SyntaxError: invalid syntax",
        task_context="Error during AST pre-check",
        created_at=None,
    )

    flow = ConfidenceApprovalFlow()
    result = await flow.process_evolution(proposal=failed_proposal)
    assert not result.approved
    assert result.requires_manual_review

    async with get_session() as db:
        result_db = await db.execute(
            select(ApprovalRecord).where(ApprovalRecord.action_type == "evolution")
        )
        approval = result_db.scalars().first()

        assert approval is not None
        assert isinstance(approval.payload, dict)
        assert approval.payload.get("confidence") == 0.0
        assert approval.payload.get("test_passed") is False

        await db.delete(approval)
        await db.commit()
