"""The judge reads the whole candidate skill, however long it is."""

from myrm_agent_harness.agent.skills.evolution.execution.evaluator import BatchEvaluator


def test_the_evaluation_prompt_holds_the_whole_candidate() -> None:
    candidate = "# Skill\n" + "A filler line of instructions.\n" * 400 + "## Last Section\nLAST-SECTION-MARKER\n"
    assert len(candidate) > 10_000

    prompt = BatchEvaluator(llm=None)._build_evaluation_prompt(candidate, "Error: exit 1", "trajectory text")

    assert prompt.count("LAST-SECTION-MARKER") == 1
    assert "trajectory text" in prompt
