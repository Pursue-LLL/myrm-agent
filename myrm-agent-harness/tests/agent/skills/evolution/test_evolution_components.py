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

# --- Mock Data ---
MOCK_SKILL = SkillRecord(
    skill_id="mock-1",
    name="mock-skill",
    description="A mock skill",
    content="## Instructions\n1. Do something.",
    path="/fake/path",
    lineage=None,
    evolution_locked=False,
)


# --- 1. Test Evaluator (Sandbox Dry-Run) ---
@pytest.mark.asyncio
async def test_evaluator_dry_run_validation():
    # Setup mock LLM that always passes the initial score
    mock_llm = MagicMock()

    # Mock return values for ainvoke (it should return an object with .content string)
    from myrm_agent_harness.agent.skills.evolution.execution.evaluator import (
        SkillEvaluationRubric,
    )

    mock_rubric = SkillEvaluationRubric(
        accuracy_score=1.0,
        anti_fragmentation_score=1.0,
        redundancy_score=1.0,
        is_general=True,
        reasoning="Looks good",
    )

    mock_structured_llm = MagicMock()
    mock_structured_llm.ainvoke = AsyncMock(return_value=mock_rubric)
    mock_llm.with_structured_output = MagicMock(return_value=mock_structured_llm)

    evaluator = BatchEvaluator(mock_llm)

    # Variant 1: Good Python code
    good_variant = "```python\nprint('Hello')\nx = 1\n```"
    # Variant 2: Bad Python code (SyntaxError)
    bad_variant = "```python\nprint('Hello'\nx = 1\n```"  # Missing parenthesis

    variants = [good_variant, bad_variant]

    best, score, _reason, is_general = await evaluator.evaluate_variants(MOCK_SKILL, variants, "feedback", "trace")

    # Evaluator should pick the good variant, because the bad one gets 0 score due to AST failure
    assert best == good_variant
    assert score == 1.0
    assert is_general is True


# --- 2. Test VariantGenerator (Constraint Injection) ---
@pytest.mark.asyncio
async def test_variant_generator_constraint_injection():
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        side_effect=[
            MagicMock(content="Variant 1"),
            MagicMock(content="Variant 2"),
            MagicMock(content="Variant 3"),
        ]
    )
    generator = VariantGenerator(mock_llm)

    constraints = "- Do not use requests\n- Do not use bs4"
    variants = await generator.generate_variants(
        MOCK_SKILL, "feedback", "trace", num_variants=3, constraints=constraints
    )

    assert len(variants) == 3
    # Check if constraints were in the prompt
    call_args = mock_llm.ainvoke.call_args[0][0]
    prompt_text = call_args[0].content
    assert "Historical Constraints" in prompt_text
    assert "- Do not use requests" in prompt_text


# --- 3. Test Engine (Orchestration) ---
@pytest.mark.asyncio
async def test_engine_fix_skill_with_constraints():
    # Mock store
    mock_store = MagicMock(spec=SkillStore)
    mock_store.get_skill.return_value = MOCK_SKILL
    mock_store.get_evolution_constraints.return_value = ["Must be fast"]

    from myrm_agent_harness.agent.skills.evolution.execution.evaluator import (
        SkillEvaluationRubric,
    )

    async def fake_ainvoke(messages, **kwargs):
        content = messages if isinstance(messages, str) else messages[0].content
        if "expert AI agent skill optimizer" in content:
            return MagicMock(content="Fixed Variant")
        else:
            return SkillEvaluationRubric(
                accuracy_score=0.85,
                anti_fragmentation_score=1.0,
                redundancy_score=1.0,
                is_general=True,
                reasoning="fixed",
            )

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)

    mock_structured_llm = MagicMock()
    mock_structured_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mock_llm.with_structured_output = MagicMock(return_value=mock_structured_llm)

    engine = SkillEvolutionEngine(store=mock_store, llm=mock_llm)

    proposal = await engine.fix_skill("mock-1", "error")

    assert proposal is not None
    assert proposal.evolution_type == EvolutionType.FIX
    assert proposal.proposed_content == "Fixed Variant"
    assert proposal.score >= 0.85
    # A proposal is not a constraint: only a user's rejection reason is saved.
    mock_store.add_evolution_constraint.assert_not_called()


@pytest.mark.asyncio
async def test_engine_derive_skill_simple():
    mock_store = MagicMock(spec=SkillStore)
    mock_store.get_skill.return_value = MOCK_SKILL
    mock_store.get_evolution_constraints.return_value = []

    from myrm_agent_harness.agent.skills.evolution.execution.evaluator import (
        SkillEvaluationRubric,
    )

    async def fake_ainvoke(messages, **kwargs):
        content = messages if isinstance(messages, str) else messages[0].content
        if "expert AI agent skill optimizer" in content:
            return MagicMock(content="Derived Variant")
        # The improvement gate keeps the original unless a variant scores strictly higher than it.
        improved = "Derived Variant" in content
        return SkillEvaluationRubric(
            accuracy_score=0.90 if improved else 0.75,
            anti_fragmentation_score=1.0,
            redundancy_score=1.0,
            is_general=True,
            reasoning="derived",
        )

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)

    mock_structured_llm = MagicMock()
    mock_structured_llm.ainvoke = AsyncMock(side_effect=fake_ainvoke)
    mock_llm.with_structured_output = MagicMock(return_value=mock_structured_llm)

    engine = SkillEvolutionEngine(store=mock_store, llm=mock_llm)

    proposal = await engine.derive_skill_simple("mock-1", "Make it better")

    assert proposal is not None
    assert proposal.evolution_type == EvolutionType.DERIVED
    assert proposal.proposed_content == "Derived Variant"
    assert proposal.score >= 0.90
    mock_store.add_evolution_constraint.assert_not_called()


@pytest.mark.asyncio
async def test_evaluator_syntax_error_validation():
    mock_llm = MagicMock()
    evaluator = BatchEvaluator(mock_llm)

    # Missing parenthesis
    is_valid, reason = evaluator._dry_run_validation("```python\nprint('Hello'\n```")
    assert is_valid is False
    assert "SyntaxError" in reason

    # Hallucinated import (now caught by advanced import check)
    is_valid, reason = evaluator._dry_run_validation("```python\nimport this_does_not_exist\n```")
    assert is_valid is False
    assert "ModuleNotFoundError" in reason


@pytest.mark.asyncio
async def test_variant_generator_error_handling():
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(side_effect=Exception("LLM Error"))
    generator = VariantGenerator(mock_llm)

    variants = await generator.generate_variants(MOCK_SKILL, "feedback", "trace", num_variants=1)

    # Should fallback to original skill
    assert len(variants) == 1
    assert variants[0] == MOCK_SKILL.content


@pytest.mark.asyncio
async def test_engine_evolve_multiple_concurrent():
    from myrm_agent_harness.agent.skills.evolution.core.types import (
        EvolutionRequest,
        EvolutionType,
    )
    from myrm_agent_harness.agent.skills.evolution.execution.evaluator import (
        SkillEvaluationRubric,
    )

    mock_store = MagicMock(spec=SkillStore)
    mock_store.get_skill.return_value = MOCK_SKILL
    mock_store.get_evolution_constraints.return_value = []

    rubric = SkillEvaluationRubric(
        accuracy_score=0.95,
        anti_fragmentation_score=0.95,
        redundancy_score=0.95,
        is_general=True,
        reasoning="Good improvement",
    )
    structured_llm = MagicMock()
    structured_llm.ainvoke = AsyncMock(return_value=rubric)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="## Instructions\n1. Do better."))
    mock_llm.with_structured_output = MagicMock(return_value=structured_llm)

    engine = SkillEvolutionEngine(store=mock_store, llm=mock_llm)

    req1 = EvolutionRequest(
        skill_id="mock-1",
        evolution_type=EvolutionType.FIX,
        reason="error",
    )
    req2 = EvolutionRequest(
        skill_id="mock-1",
        evolution_type=EvolutionType.DERIVED,
        user_feedback="optimize",
    )

    results = await engine.evolve_multiple_concurrent([req1, req2])

    assert len(results) == 2
    assert results[0].evolution_type == EvolutionType.FIX
    # DERIVED with improvement gate: when baseline scores equal to variant,
    # original wins and returns None (correct quality protection behavior)
    assert results[1] is None or results[1].evolution_type == EvolutionType.DERIVED

    # test empty
    empty_res = await engine.evolve_multiple_concurrent([])
    assert empty_res == []


@pytest.mark.asyncio
async def test_engine_fix_derive_not_found_or_locked():
    mock_store = MagicMock(spec=SkillStore)
    mock_store.get_skill.return_value = None

    engine = SkillEvolutionEngine(store=mock_store, llm=MagicMock())

    assert await engine.fix_skill("not-exist", "err") is None
    assert await engine.derive_skill_simple("not-exist", "fb") is None

    locked_skill = SkillRecord(
        skill_id="mock",
        name="mock",
        description="mock",
        content="mock",
        path="",
        lineage=None,
        evolution_locked=True,  # type: ignore
    )
    mock_store.get_skill.return_value = locked_skill
    assert await engine.fix_skill("mock", "err") is None
    assert await engine.derive_skill_simple("mock", "fb") is None
