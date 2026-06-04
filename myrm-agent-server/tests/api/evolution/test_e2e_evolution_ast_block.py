import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionProposal, EvolutionType
from sqlalchemy import select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.agent.confidence_approval_flow import ConfidenceApprovalFlow
from app.services.skills.evolution_reviews import approval_to_evolution_review_record


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
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type == "evolution")
            .order_by(ApprovalRecord.created_at.desc())
        )
        approval = None
        review = None
        for record in result_db.scalars().all():
            parsed = approval_to_evolution_review_record(record)
            if parsed is not None and parsed.skill_id == failed_proposal.skill_id:
                approval = record
                review = parsed
                break

        assert approval is not None
        assert review is not None
        assert review.confidence == 0.0
        assert review.test_passed is False

        await db.delete(approval)
        await db.commit()
