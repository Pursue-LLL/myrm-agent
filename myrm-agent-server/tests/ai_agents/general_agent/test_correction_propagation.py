"""Tests for implicit feedback detection and correction propagation.

Covers: make_correction_propagation_callback, _run_correction_propagation,
implicit_feedback pipeline (detect_implicit_feedback, plan_memory_corrections),
and the composite _build_session_cleanup_callback.

Integration tests use real LLM calls via LITE_MODEL environment variable.
"""

import os
from typing import Any

import pytest
from dotenv import load_dotenv

load_dotenv(override=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def lite_llm_func():
    """Build a real LLM function using LITE_MODEL for integration tests."""
    from myrm_agent_harness.api.hooks import (
        create_extraction_llm_func,
    )

    api_key = os.getenv("LITE_API_KEY")
    base_url = os.getenv("LITE_BASE_URL")
    raw_model = os.getenv("LITE_MODEL")
    if not api_key or not raw_model:
        pytest.skip("LITE_API_KEY / LITE_MODEL not configured")

    model = raw_model.split("/", 1)[-1] if "/" in raw_model else raw_model

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        max_tokens=512,
    )
    return create_extraction_llm_func(llm)


@pytest.fixture()
def correction_messages() -> list[dict[str, str]]:
    """Conversation where user corrects a factual mistake."""
    return [
        {"role": "user", "content": "Tell me about our company MindForge"},
        {"role": "assistant", "content": "MindForce is an AI company that focuses on..."},
        {"role": "user", "content": "That's wrong! Our company name is MindForge, not MindForce."},
        {"role": "assistant", "content": "I apologize for the mistake. MindForge is..."},
    ]


@pytest.fixture()
def implicit_correction_messages() -> list[dict[str, str]]:
    """Conversation where user implicitly corrects without explicit negation."""
    return [
        {"role": "user", "content": "Can you help me with my work at ByteDance?"},
        {"role": "assistant", "content": "Sure! Since you work at ByteDance, I can help with..."},
        {"role": "user", "content": "Actually I left ByteDance last month. I'm at Google now."},
        {"role": "assistant", "content": "Got it, let me help you with your Google work."},
    ]


@pytest.fixture()
def no_correction_messages() -> list[dict[str, str]]:
    """Normal conversation without corrections."""
    return [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a high-level programming language."},
        {"role": "user", "content": "Thanks, that's helpful!"},
    ]


@pytest.fixture()
def zh_correction_messages() -> list[dict[str, str]]:
    """Chinese conversation where user corrects a mistake."""
    return [
        {"role": "user", "content": "介绍一下我们公司的产品 MindForge"},
        {"role": "assistant", "content": "MindForce 是一款..."},
        {"role": "user", "content": "你搞错了，是 MindForge 不是 MindForce"},
        {"role": "assistant", "content": "抱歉，MindForge 是..."},
    ]


# ---------------------------------------------------------------------------
# Unit tests (no LLM / no DB)
# ---------------------------------------------------------------------------


class TestDetectCorrectionSignals:
    """Test correction detection via Harness-layer detect_feedback_signals."""

    def test_english_correction_detected(self, correction_messages: list[dict[str, str]]) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals(correction_messages) == FeedbackSignal.NEGATIVE

    def test_chinese_correction_detected(self, zh_correction_messages: list[dict[str, str]]) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals(zh_correction_messages) == FeedbackSignal.NEGATIVE

    def test_no_correction_returns_none(self, no_correction_messages: list[dict[str, str]]) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        signal = detect_feedback_signals(no_correction_messages)
        assert signal != FeedbackSignal.NEGATIVE

    def test_positive_feedback_returns_positive(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        messages = [
            {"role": "user", "content": "Write a poem"},
            {"role": "assistant", "content": "Roses are red..."},
            {"role": "user", "content": "That's exactly right, perfect!"},
        ]
        assert detect_feedback_signals(messages) == FeedbackSignal.POSITIVE

    def test_empty_messages_safe(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals([]) == FeedbackSignal.NONE

    def test_single_message_safe(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        assert detect_feedback_signals([{"role": "user", "content": "hello"}]) == FeedbackSignal.NONE


class TestImplicitFeedbackUnit:
    """Unit tests for the implicit_feedback module (no LLM)."""

    @pytest.mark.asyncio
    async def test_short_messages_return_none(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        async def dummy_llm(system: str, prompt: str) -> str:
            raise AssertionError("Should not call LLM for short messages")

        result = await detect_implicit_feedback(
            [{"role": "user", "content": "hi"}], dummy_llm
        )
        assert not result.has_implicit_contradiction
        assert result.proposals == []

    @pytest.mark.asyncio
    async def test_regex_negative_skips_detection_llm(self, correction_messages: list[dict[str, str]]) -> None:
        """When regex catches NEGATIVE, LLM detection is skipped (only planning runs)."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        call_count = {"detection": 0, "planning": 0}

        async def tracking_llm(system: str, prompt: str) -> str:
            if "implicit feedback analyst" in system:
                call_count["detection"] += 1
            else:
                call_count["planning"] += 1
            return "[]"

        result = await detect_implicit_feedback(correction_messages, tracking_llm)
        assert result.signal == FeedbackSignal.NEGATIVE
        assert call_count["detection"] == 0, "Detection LLM should be skipped"
        assert call_count["planning"] == 1, "Planning LLM should be called"

    def test_parse_plan_response_handles_valid_json(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            CorrectionAction,
            _parse_plan_response,
        )

        raw = '[{"action":"update","memory_type":"semantic","content":"User works at Google","confidence":0.9,"reasoning":"User stated they moved to Google"}]'
        proposals = _parse_plan_response(raw)
        assert len(proposals) == 1
        assert proposals[0].action == CorrectionAction.UPDATE
        assert proposals[0].content == "User works at Google"
        assert proposals[0].confidence == 0.9

    def test_parse_plan_response_handles_invalid_json(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            _parse_plan_response,
        )

        proposals = _parse_plan_response("not json at all")
        assert proposals == []

    def test_parse_plan_response_skips_invalid_actions(self) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            _parse_plan_response,
        )

        raw = '[{"action":"invalid","memory_type":"semantic","content":"x","confidence":0.9,"reasoning":"y"}]'
        proposals = _parse_plan_response(raw)
        assert proposals == []


class TestCallbackFactory:
    """Test make_correction_propagation_callback factory."""

    def test_returns_callable(self) -> None:
        from app.ai_agents.general_agent.callbacks import make_correction_propagation_callback

        async def dummy_llm(system: str, prompt: str) -> str:
            return '{"has_contradiction": false, "signals": []}'

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=dummy_llm)
        assert callable(cb)

    @pytest.mark.asyncio
    async def test_callback_handles_no_correction_gracefully(self) -> None:
        """When no correction is detected, callback should return without error."""
        from app.ai_agents.general_agent.callbacks import make_correction_propagation_callback

        async def dummy_llm(system: str, prompt: str) -> str:
            return '{"has_contradiction": false, "signals": []}'

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=dummy_llm)
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "What is Python?"},
            {"role": "assistant", "content": "Python is a programming language."},
        ]
        await cb(messages, "chat-123")

    @pytest.mark.asyncio
    async def test_callback_handles_exception_gracefully(self) -> None:
        """Callback should catch exceptions and not propagate them."""
        from app.ai_agents.general_agent.callbacks import make_correction_propagation_callback

        async def failing_llm(system: str, prompt: str) -> str:
            raise RuntimeError("LLM failure")

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=failing_llm)
        messages: list[dict[str, str]] = [
            {"role": "user", "content": "Tell me about X"},
            {"role": "assistant", "content": "X is about..."},
            {"role": "user", "content": "That's wrong! X is actually Y."},
            {"role": "assistant", "content": "Sorry, Y..."},
        ]
        await cb(messages, "chat-456")


class TestRunCorrectionPropagation:
    """Test _run_correction_propagation with controlled inputs."""

    @pytest.mark.asyncio
    async def test_short_messages_returns_early(self) -> None:
        from app.ai_agents.general_agent.callbacks import _run_correction_propagation

        async def dummy_llm(system: str, prompt: str) -> str:
            raise AssertionError("LLM should not be called for short messages")

        await _run_correction_propagation(
            [{"role": "user", "content": "hi"}],
            agent_id="test",
            llm_func=dummy_llm,
            chat_id=None,
        )

    @pytest.mark.asyncio
    async def test_no_negative_feedback_returns_early(self, no_correction_messages: list[dict[str, str]]) -> None:
        from app.ai_agents.general_agent.callbacks import _run_correction_propagation

        async def dummy_llm(system: str, prompt: str) -> str:
            return '{"has_contradiction": false, "signals": []}'

        await _run_correction_propagation(
            no_correction_messages,
            agent_id="test",
            llm_func=dummy_llm,
            chat_id=None,
        )


class TestDefaultPolicy:
    """Test that _DEFAULT_POLICY includes correction_auto_approve."""

    def test_correction_auto_approve_in_default_policy(self) -> None:
        from app.services.memory.shared_context import _DEFAULT_POLICY

        assert "correction_auto_approve" in _DEFAULT_POLICY
        assert _DEFAULT_POLICY["correction_auto_approve"] is True


class TestCorrectionSourceId:
    def test_build_correction_proposal_source_id_is_stable(self) -> None:
        from app.ai_agents.general_agent.callbacks import build_correction_proposal_source_id

        first = build_correction_proposal_source_id("chat-1", "API version is v3")
        second = build_correction_proposal_source_id("chat-1", "API version is v3")
        assert first == second
        assert first.startswith("chat-1:")

    def test_build_correction_proposal_source_id_varies_by_summary(self) -> None:
        from app.ai_agents.general_agent.callbacks import build_correction_proposal_source_id

        first = build_correction_proposal_source_id("chat-1", "Use gRPC")
        second = build_correction_proposal_source_id("chat-1", "Use REST")
        assert first != second


# ---------------------------------------------------------------------------
# Integration tests (real LLM, no mock)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("LITE_API_KEY"),
    reason="LITE_API_KEY not configured for integration tests",
)
class TestImplicitFeedbackIntegration:
    """Integration tests for implicit feedback detection with real LLM."""

    @pytest.mark.asyncio
    async def test_detects_explicit_correction_and_plans(
        self, lite_llm_func: Any, correction_messages: list[dict[str, str]]
    ) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        result = await detect_implicit_feedback(correction_messages, lite_llm_func)
        assert result.signal == FeedbackSignal.NEGATIVE
        assert len(result.proposals) > 0, "Should produce correction proposals"
        lower_content = " ".join(p.content.lower() for p in result.proposals)
        assert "mindforge" in lower_content or "mindforce" in lower_content

    @pytest.mark.asyncio
    async def test_detects_implicit_contradiction(
        self, lite_llm_func: Any, implicit_correction_messages: list[dict[str, str]]
    ) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        result = await detect_implicit_feedback(implicit_correction_messages, lite_llm_func)
        assert result.signal == FeedbackSignal.NEGATIVE
        assert result.has_implicit_contradiction is True
        assert len(result.proposals) > 0

    @pytest.mark.asyncio
    async def test_no_false_positives_for_normal_conversation(
        self, lite_llm_func: Any, no_correction_messages: list[dict[str, str]]
    ) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        result = await detect_implicit_feedback(no_correction_messages, lite_llm_func)
        assert result.signal != FeedbackSignal.NEGATIVE

    @pytest.mark.asyncio
    async def test_chinese_correction_plans(
        self, lite_llm_func: Any, zh_correction_messages: list[dict[str, str]]
    ) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        result = await detect_implicit_feedback(zh_correction_messages, lite_llm_func)
        assert result.signal == FeedbackSignal.NEGATIVE
        assert len(result.proposals) > 0


@pytest.mark.skipif(
    not os.getenv("LITE_API_KEY"),
    reason="LITE_API_KEY not configured for integration tests",
)
class TestCorrectionPropagationEndToEnd:
    """End-to-end test: correction detection → proposal planning."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_correction(
        self, lite_llm_func: Any, correction_messages: list[dict[str, str]]
    ) -> None:
        """Verify the full pipeline from detection to proposal generation."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            plan_memory_corrections,
        )

        signal = detect_feedback_signals(correction_messages)
        assert signal == FeedbackSignal.NEGATIVE, "Should detect correction"

        proposals = await plan_memory_corrections(correction_messages, lite_llm_func)
        assert len(proposals) > 0, "Should produce correction proposals"
        for p in proposals:
            assert p.content.strip(), "Proposal content should not be empty"
            assert p.confidence >= 0.5
        print(f"\nCorrection proposals: {[p.content for p in proposals]}")

    def test_full_pipeline_without_correction(self, no_correction_messages: list[dict[str, str]]) -> None:
        """Verify the pipeline short-circuits when no correction is detected."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        signal = detect_feedback_signals(no_correction_messages)
        assert signal != FeedbackSignal.NEGATIVE, "Should NOT detect correction"
