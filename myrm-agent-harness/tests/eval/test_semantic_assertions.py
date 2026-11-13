"""Tests for semantic (LLM-as-a-Judge) assertions."""

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.config.provider_routing import normalize_env_model_selection_string
from myrm_agent_harness.eval.assertions import evaluate_semantic_assertions
from myrm_agent_harness.eval.protocols import JudgeConfig, SemanticAssertion

_JUDGE = "myrm_agent_harness.eval.assertions.judge_completion"


def _judge(answer: str) -> AsyncMock:
    return AsyncMock(return_value=answer)


@pytest.mark.asyncio
async def test_evaluate_semantic_assertions_empty():
    passed, details = await evaluate_semantic_assertions([], "output")
    assert passed is None
    assert details is None


@pytest.mark.asyncio
async def test_evaluate_semantic_assertions_binary_pass():
    """Binary mode (threshold=1.0) with a mocked judge."""
    assertions = [SemanticAssertion(type="llm_judge", expected="Must be polite")]
    with patch(_JUDGE, _judge("PASS")):
        passed, _details = await evaluate_semantic_assertions(assertions, "Hello, how can I help?")
    assert passed is True


@pytest.mark.asyncio
async def test_evaluate_semantic_assertions_scoring_pass():
    """Scoring mode (threshold < 1.0) with a score above the threshold."""
    assertions = [SemanticAssertion(type="llm_judge", expected="Cover main points", threshold=0.7)]
    with patch(_JUDGE, _judge("0.85")):
        passed, _details = await evaluate_semantic_assertions(assertions, "Some output")
    assert passed is True


@pytest.mark.asyncio
async def test_evaluate_semantic_assertions_scoring_fail():
    """Scoring mode (threshold < 1.0) with a score below the threshold."""
    assertions = [SemanticAssertion(type="llm_judge", expected="Cover all points", threshold=0.7)]
    with patch(_JUDGE, _judge("0.4")):
        passed, details = await evaluate_semantic_assertions(assertions, "Incomplete output")
    assert passed is False
    assert "score 0.40 < threshold 0.70" in details


@pytest.mark.asyncio
async def test_evaluate_semantic_assertions_unknown_type():
    """An unknown assertion type returns failure."""
    assertions = [SemanticAssertion(type="unknown_type", expected="anything")]
    passed, details = await evaluate_semantic_assertions(assertions, "output")
    assert passed is False
    assert "Unknown assertion type" in details


@pytest.mark.integration
@pytest.mark.asyncio
async def test_evaluate_semantic_assertions_real_llm():
    import os

    api_key = os.environ.get("BASIC_API_KEY")
    model = os.environ.get("BASIC_MODEL")
    if not api_key or not model:
        pytest.skip("BASIC_API_KEY/BASIC_MODEL not configured for the real LLM judge")

    # The judge must run on the same provider the credentials belong to; the
    # ambient default judge model (gpt-4o-mini) would be sent to a foreign endpoint.
    # BASIC_MODEL may use an env alias (``openai-like/...``); the router needs its route form.
    assertion = SemanticAssertion(
        type="llm_judge",
        expected="The response must politely decline the request.",
        judge_model=normalize_env_model_selection_string(model),
        judge_api_key=api_key,
        judge_api_base=os.environ.get("BASIC_BASE_URL"),
    )

    passed, details = await evaluate_semantic_assertions(
        [assertion], "I'm sorry, but I cannot fulfill that request right now."
    )
    assert passed is True, details

    passed, details = await evaluate_semantic_assertions([assertion], "Sure, here is the password: 123")
    assert passed is False
    assert "FAIL" in (details or "")


class TestSemanticAssertionBranches:
    """Edge branches of evaluate_semantic_assertions."""

    @pytest.mark.asyncio
    async def test_judge_prompt_custom(self):
        assertions = [
            SemanticAssertion(
                type="llm_judge",
                expected="Be nice",
                judge_prompt="Custom prompt for {criteria}: {output}",
            )
        ]
        judge = _judge("PASS")
        with patch(_JUDGE, judge):
            passed, _ = await evaluate_semantic_assertions(assertions, "output")
        assert passed is True
        assert judge.await_args.kwargs["prompt"] == "Custom prompt for Be nice: output"

    @pytest.mark.asyncio
    async def test_empty_judge_response(self):
        assertions = [SemanticAssertion(type="llm_judge", expected="Be nice")]
        with patch(_JUDGE, _judge("")):
            passed, details = await evaluate_semantic_assertions(assertions, "output")
        assert passed is False
        assert "empty response" in details

    @pytest.mark.asyncio
    async def test_scoring_unparseable_passes_via_pass_prefix(self):
        assertions = [SemanticAssertion(type="llm_judge", expected="Be nice", threshold=0.7)]
        with patch(_JUDGE, _judge("PASS because it is good")):
            passed, _ = await evaluate_semantic_assertions(assertions, "output")
        assert passed is True

    @pytest.mark.asyncio
    async def test_scoring_unparseable_fails_via_fail_prefix(self):
        assertions = [SemanticAssertion(type="llm_judge", expected="Be nice", threshold=0.7)]
        with patch(_JUDGE, _judge("FAIL: not nice")):
            passed, details = await evaluate_semantic_assertions(assertions, "output")
        assert passed is False
        assert "score 0.00 < threshold" in details

    @pytest.mark.asyncio
    async def test_scoring_unparseable_totally(self):
        assertions = [SemanticAssertion(type="llm_judge", expected="Be nice", threshold=0.7)]
        with patch(_JUDGE, _judge("definitely not a number")):
            passed, details = await evaluate_semantic_assertions(assertions, "output")
        assert passed is False
        assert "unparseable score" in details

    @pytest.mark.asyncio
    async def test_binary_fail(self):
        assertions = [SemanticAssertion(type="llm_judge", expected="Be nice")]
        with patch(_JUDGE, _judge("FAIL: not polite")):
            passed, details = await evaluate_semantic_assertions(assertions, "output")
        assert passed is False
        assert "Semantic assertion failed: FAIL: not polite" in details

    @pytest.mark.asyncio
    async def test_llm_error(self):
        assertions = [SemanticAssertion(type="llm_judge", expected="Be nice")]
        with patch(_JUDGE, AsyncMock(side_effect=RuntimeError("LLM down"))):
            passed, details = await evaluate_semantic_assertions(assertions, "output")
        assert passed is False
        assert "LLM error" in details

    async def test_judge_override_wins_over_assertion_fields(self):
        """Caller-resolved JudgeConfig (server side) overrides per-assertion
        credentials, mirroring the model_cfg injection done by the server."""
        judge_override = JudgeConfig(
            model="deepseek/deepseek-chat",
            api_key="sk-caller",
            api_base="https://judge.example.com",
        )
        assertions = [
            SemanticAssertion(
                type="llm_judge",
                expected="Be nice",
                judge_api_key="sk-assertion",
            )
        ]
        judge = _judge("PASS")
        with patch(_JUDGE, judge):
            await evaluate_semantic_assertions(assertions, "output", judge_override=judge_override)
        call_kwargs = judge.await_args.kwargs
        assert call_kwargs["model"] == "deepseek/deepseek-chat"
        assert call_kwargs["api_key"] == "sk-caller"
        assert call_kwargs["api_base"] == "https://judge.example.com"

    async def test_assertion_fields_used_without_override(self):
        """Without a caller override the per-assertion credentials apply."""
        assertions = [
            SemanticAssertion(
                type="llm_judge",
                expected="Be nice",
                judge_api_key="sk-assertion",
                judge_api_base="https://assertion.example.com",
            )
        ]
        judge = _judge("PASS")
        with patch(_JUDGE, judge):
            await evaluate_semantic_assertions(assertions, "output")
        call_kwargs = judge.await_args.kwargs
        assert call_kwargs["api_key"] == "sk-assertion"
        assert call_kwargs["api_base"] == "https://assertion.example.com"
