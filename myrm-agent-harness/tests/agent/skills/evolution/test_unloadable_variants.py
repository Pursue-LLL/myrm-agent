"""A variant the skill loader would skip never becomes a proposal.

A skill the loader skips vanishes from the agent's skill list, so the evaluator scores such a variant 0.0
and the proposal builder drops it, however well the judge rates its text.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.proposal_builder import ProposalBuilder, unloadable_reason
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.agent.skills.evolution.execution.evaluator import (
    BatchEvaluator,
    SkillEvaluationRubric,
)

_LOADABLE = "---\ndescription: Deploys the service.\n---\n# Deploy\nRun the deploy script.\n"
_EDIT_SUMMARY = '---EDIT_SUMMARY---\n{"preserved_sections": ["all"], "changed_sections": [], "notes": "fixed"}'

_UNLOADABLE = {
    "no-frontmatter": "# Deploy\nRun the deploy script.\n",
    "text-before-frontmatter": f"Here is the updated skill:\n{_LOADABLE}",
    "unclosed-frontmatter": "---\ndescription: Deploys the service.\n# Deploy\n",
    "invalid-yaml": "---\ndescription: Use when: a colon breaks the YAML\n---\nbody\n",
    "no-description": "---\nname: deploy\n---\nbody\n",
    "empty": "",
}


def _skill(content: str = _LOADABLE) -> SkillRecord:
    return SkillRecord(
        skill_id="deploy-1",
        name="deploy",
        description="Deploys the service.",
        content=content,
        path="skills/deploy/SKILL.md",
        lineage=None,
    )


def _generous_judge() -> MagicMock:
    """A judge that rates every candidate perfectly, so only the loadability gate can tell variants apart."""
    rubric = SkillEvaluationRubric(
        accuracy_score=1.0,
        anti_fragmentation_score=1.0,
        redundancy_score=1.0,
        is_general=True,
        reasoning="Looks good",
    )
    structured = MagicMock()
    structured.ainvoke = AsyncMock(return_value=rubric)
    llm = MagicMock()
    llm.with_structured_output = MagicMock(return_value=structured)
    llm.structured = structured
    return llm


@pytest.mark.parametrize("content", _UNLOADABLE.values(), ids=_UNLOADABLE.keys())
def test_content_the_loader_would_skip_has_a_reason(content: str) -> None:
    assert unloadable_reason(content, "deploy")


def test_content_the_loader_accepts_has_no_reason() -> None:
    assert unloadable_reason(_LOADABLE, "deploy") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("content", _UNLOADABLE.values(), ids=_UNLOADABLE.keys())
async def test_the_evaluator_prefers_a_loadable_variant_over_one_the_judge_likes_just_as_much(content: str) -> None:
    judge = _generous_judge()

    best, score, _reason, _is_general = await BatchEvaluator(judge).evaluate_variants(
        _skill(), [content, _LOADABLE], "feedback", "trace"
    )

    assert best == _LOADABLE
    assert score == 1.0
    assert judge.structured.ainvoke.await_count == 1  # the unloadable variant was not even sent to the judge


@pytest.mark.asyncio
async def test_the_evaluator_scores_zero_when_no_variant_is_loadable() -> None:
    _best, score, reason, is_general = await BatchEvaluator(_generous_judge()).evaluate_variants(
        _skill(), [_UNLOADABLE["no-frontmatter"], _UNLOADABLE["no-description"]], "feedback", "trace"
    )

    assert score == 0.0
    assert "Not a loadable SKILL.md" in reason
    assert is_general is False


@pytest.mark.asyncio
async def test_a_variant_is_judged_without_its_edit_summary_tail() -> None:
    _best, score, _reason, _is_general = await BatchEvaluator(_generous_judge()).evaluate_variants(
        _skill(), [f"{_LOADABLE}{_EDIT_SUMMARY}"], "feedback", "trace"
    )

    assert score == 1.0


@pytest.mark.parametrize("content", _UNLOADABLE.values(), ids=_UNLOADABLE.keys())
def test_the_builder_makes_no_proposal_from_an_unloadable_variant(content: str) -> None:
    proposal = ProposalBuilder().build_proposal(
        skill=_skill(),
        evolution_type=EvolutionType.FIX,
        best_variant=content,
        score=0.9,
        reasoning="Fixed",
    )

    assert proposal is None


def test_the_builder_checks_the_variant_without_its_edit_summary_tail() -> None:
    proposal = ProposalBuilder().build_proposal(
        skill=_skill(),
        evolution_type=EvolutionType.FIX,
        best_variant=f"{_LOADABLE}{_EDIT_SUMMARY}",
        score=0.9,
        reasoning="Fixed",
    )

    assert proposal is not None
    assert proposal.proposed_content == _LOADABLE.rstrip()
    assert proposal.edit_summary is not None


@pytest.mark.asyncio
async def test_a_fix_whose_variants_are_all_unloadable_yields_no_proposal() -> None:
    store = MagicMock(spec=SkillStore)
    store.get_skill.return_value = _skill()
    store.get_evolution_constraints.return_value = []
    judge = _generous_judge()
    judge.ainvoke = AsyncMock(return_value=MagicMock(content=_UNLOADABLE["text-before-frontmatter"]))

    proposal = await SkillEvolutionEngine(store=store, llm=judge).fix_skill("deploy-1", "error")

    assert proposal is None
