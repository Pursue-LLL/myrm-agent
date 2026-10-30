"""The edit summary a variant carries: the proposal builder splits it off, the evaluator strips it before scoring."""

import pytest

from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.execution.evaluator import BatchEvaluator

_UPDATED_SKILL_MD = "---\ndescription: The updated skill.\n---\nUpdated skill content here"


@pytest.mark.asyncio
async def test_proposal_builder_split_edit_summary():
    """ProposalBuilder correctly extracts edit_summary from variant content."""
    from myrm_agent_harness.agent.skills.evolution.core.proposal_builder import (
        ProposalBuilder,
    )

    builder = ProposalBuilder()
    skill = SkillRecord(
        skill_id="s1",
        name="test-skill",
        description="desc",
        content="original content",
        path="/fake",
        lineage=None,
    )
    variant_with_summary = (
        f"{_UPDATED_SKILL_MD}\n---EDIT_SUMMARY---\n"
        '{"preserved_sections": ["setup"], "changed_sections": ["validation"], "notes": "fixed"}'
    )
    proposal = builder.build_proposal(
        skill=skill,
        evolution_type=EvolutionType.FIX,
        best_variant=variant_with_summary,
        score=0.9,
        reasoning="Good fix",
    )
    assert proposal.proposed_content == _UPDATED_SKILL_MD
    assert proposal.edit_summary is not None
    assert proposal.edit_summary["changed_sections"] == ["validation"]


@pytest.mark.asyncio
async def test_proposal_builder_split_edit_summary_malformed():
    """ProposalBuilder tolerates malformed edit_summary JSON (trailing comma / bare newline)."""
    from myrm_agent_harness.agent.skills.evolution.core.proposal_builder import (
        ProposalBuilder,
    )

    builder = ProposalBuilder()
    skill = SkillRecord(
        skill_id="s2",
        name="test-skill-2",
        description="desc",
        content="original content",
        path="/fake",
        lineage=None,
    )
    variant_with_summary = (
        f"{_UPDATED_SKILL_MD}\n---EDIT_SUMMARY---\n"
        '{"preserved_sections": ["setup"], "changed_sections": ["validation"], "notes": "fixed",}'
    )
    proposal = builder.build_proposal(
        skill=skill,
        evolution_type=EvolutionType.FIX,
        best_variant=variant_with_summary,
        score=0.9,
        reasoning="Good fix",
    )
    assert proposal.proposed_content == _UPDATED_SKILL_MD
    assert proposal.edit_summary is not None
    assert proposal.edit_summary["changed_sections"] == ["validation"]


@pytest.mark.asyncio
async def test_evaluator_strip_edit_summary():
    """BatchEvaluator._strip_edit_summary removes the metadata block."""
    evaluator = BatchEvaluator(llm=None)
    content_with_summary = 'Skill content body\n---EDIT_SUMMARY---\n{"preserved_sections": ["all"]}'
    stripped = evaluator._strip_edit_summary(content_with_summary)
    assert stripped == "Skill content body"
    assert "EDIT_SUMMARY" not in stripped

    content_without = "Clean skill content"
    assert evaluator._strip_edit_summary(content_without) == "Clean skill content"
