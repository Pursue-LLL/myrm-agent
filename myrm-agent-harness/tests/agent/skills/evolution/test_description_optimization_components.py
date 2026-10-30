"""OPTIMIZE_DESCRIPTION pipeline: proposal building, variant generation, scoring and engine entry point."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.agent.skills.evolution.execution.evaluator import BatchEvaluator
from myrm_agent_harness.agent.skills.evolution.pipeline.variant_generator import (
    VariantGenerator,
)


@pytest.mark.asyncio
async def test_proposal_builder_optimize_description_semantics():
    """ProposalBuilder uses skill.description (not content) for OPTIMIZE_DESCRIPTION."""
    from myrm_agent_harness.agent.skills.evolution.core.proposal_builder import (
        ProposalBuilder,
    )

    builder = ProposalBuilder()
    skill = SkillRecord(
        skill_id="s1",
        name="test-skill",
        description="Old description for matching",
        content="## Full Skill Body\n1. Step one\n2. Step two",
        path="/fake",
        lineage=None,
    )
    proposal = builder.build_proposal(
        skill=skill,
        evolution_type=EvolutionType.OPTIMIZE_DESCRIPTION,
        best_variant="Use when: coding tasks. NOT for: writing tasks.",
        score=0.85,
        reasoning="Better triggers",
        is_general=True,
    )
    assert proposal.original_content == "Old description for matching"
    assert proposal.proposed_content == "Use when: coding tasks. NOT for: writing tasks."
    assert "Old description" in proposal.diff
    assert "Use when:" in proposal.diff
    assert "## Full Skill Body" not in proposal.original_content


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
        "Updated skill content here\n---EDIT_SUMMARY---\n"
        '{"preserved_sections": ["setup"], "changed_sections": ["validation"], "notes": "fixed"}'
    )
    proposal = builder.build_proposal(
        skill=skill,
        evolution_type=EvolutionType.FIX,
        best_variant=variant_with_summary,
        score=0.9,
        reasoning="Good fix",
    )
    assert proposal.proposed_content == "Updated skill content here"
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
        "Updated skill content here\n---EDIT_SUMMARY---\n"
        '{"preserved_sections": ["setup"], "changed_sections": ["validation"], "notes": "fixed",}'
    )
    proposal = builder.build_proposal(
        skill=skill,
        evolution_type=EvolutionType.FIX,
        best_variant=variant_with_summary,
        score=0.9,
        reasoning="Good fix",
    )
    assert proposal.proposed_content == "Updated skill content here"
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


@pytest.mark.asyncio
async def test_evaluate_description_variants():
    """evaluate_description_variants scores description variants."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = '{"score": 0.9, "reasoning": "Good triggers"}'
    mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

    evaluator = BatchEvaluator(llm=mock_llm)
    skill = SkillRecord(
        skill_id="s1",
        name="test-skill",
        description="Old desc",
        content="body",
        path="/fake",
        lineage=None,
    )
    variants = [
        "Use when: X tasks. NOT for: Y tasks.",
        "Use when: A tasks. NOT for: B tasks.",
    ]
    best_desc, score, _reason, is_general = await evaluator.evaluate_description_variants(
        original_skill=skill, variants=variants
    )
    assert best_desc in variants
    assert score == 0.9
    assert is_general is True


@pytest.mark.asyncio
async def test_generate_description_variants():
    """VariantGenerator.generate_description_variants generates desc variants."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = "Use when: coding. NOT for: math."
    mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

    gen = VariantGenerator(llm=mock_llm)
    skill = SkillRecord(
        skill_id="s1",
        name="code-helper",
        description="Helps with code",
        content="## Body",
        path="/fake",
        lineage=None,
    )
    variants = await gen.generate_description_variants(skill=skill, num_variants=2)
    assert len(variants) == 2
    assert all("Use when:" in v for v in variants)


@pytest.mark.asyncio
async def test_engine_optimize_description():
    """SkillEvolutionEngine.optimize_description produces correct proposal."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = "Use when: deployment. NOT for: testing."
    mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

    desc_eval_resp = MagicMock()
    desc_eval_resp.content = '{"score": 0.88, "reasoning": "Precise triggers"}'
    mock_llm.ainvoke = AsyncMock(return_value=desc_eval_resp)

    mock_store = MagicMock(spec=SkillStore)
    skill = SkillRecord(
        skill_id="s1",
        name="deploy-skill",
        description="Deploys stuff",
        content="## Deploy Guide\n1. Run deploy",
        path="/fake",
        lineage=None,
        evolution_locked=False,
    )
    mock_store.get_skill.return_value = skill

    engine = SkillEvolutionEngine(store=mock_store, llm=mock_llm)
    proposal = await engine.optimize_description(skill_id="s1")

    assert proposal is not None
    assert proposal.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION
    assert proposal.original_content == "Deploys stuff"
    assert proposal.proposed_content != ""
    assert proposal.is_general is True


@pytest.mark.asyncio
async def test_description_eval_robust_json_parsing():
    """evaluate_description_variants tolerates prose framing + trailing commas in LLM score JSON."""
    mock_llm = MagicMock()
    mock_resp = MagicMock()
    mock_resp.content = 'Here is my assessment:\n{"score": 0.9, "reasoning": "Clear trigger conditions",}'
    mock_llm.ainvoke = AsyncMock(return_value=mock_resp)

    evaluator = BatchEvaluator(llm=mock_llm)
    original = SkillRecord(
        skill_id="s1",
        name="deploy-skill",
        description="Deploys stuff",
        content="## Deploy Guide\n1. Run deploy",
        path="/fake",
        lineage=None,
        evolution_locked=False,
    )
    best_desc, score, reasoning, is_general = await evaluator.evaluate_description_variants(
        original_skill=original, variants=["Deploys things", "Runs deployments"]
    )

    assert score == 0.9
    assert reasoning == "Clear trigger conditions"
    assert is_general is True
    assert best_desc in ("Deploys things", "Runs deployments")
