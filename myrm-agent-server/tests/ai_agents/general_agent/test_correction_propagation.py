"""Tests for cross-Agent correction propagation.

Covers: make_correction_propagation_callback, _run_correction_propagation,
_extract_correction_summary, and the composite _build_session_cleanup_callback.

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
    from myrm_agent_harness.agent._internals.memory_extraction import (
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
        max_tokens=256,
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


class TestCallbackFactory:
    """Test make_correction_propagation_callback factory."""

    def test_returns_callable(self) -> None:
        from app.ai_agents.general_agent.callbacks import make_correction_propagation_callback

        async def dummy_llm(system: str, prompt: str) -> str:
            return "NONE"

        cb = make_correction_propagation_callback(agent_id="test-agent", llm_func=dummy_llm)
        assert callable(cb)

    @pytest.mark.asyncio
    async def test_callback_handles_no_correction_gracefully(self) -> None:
        """When no correction is detected, callback should return without error."""
        from app.ai_agents.general_agent.callbacks import make_correction_propagation_callback

        async def dummy_llm(system: str, prompt: str) -> str:
            return "NONE"

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
            raise AssertionError("LLM should not be called when no correction")

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


class TestPromptTemplates:
    """Test correction summary prompt templates."""

    def test_system_prompt_mentions_none(self) -> None:
        from app.ai_agents.general_agent.callbacks import _CORRECTION_SUMMARY_SYSTEM

        assert "NONE" in _CORRECTION_SUMMARY_SYSTEM

    def test_prompt_template_has_placeholders(self) -> None:
        from app.ai_agents.general_agent.callbacks import _CORRECTION_SUMMARY_PROMPT_TEMPLATE

        assert "{n}" in _CORRECTION_SUMMARY_PROMPT_TEMPLATE
        assert "{conversation}" in _CORRECTION_SUMMARY_PROMPT_TEMPLATE

    def test_prompt_template_formats_correctly(self) -> None:
        from app.ai_agents.general_agent.callbacks import _CORRECTION_SUMMARY_PROMPT_TEMPLATE

        result = _CORRECTION_SUMMARY_PROMPT_TEMPLATE.format(n=4, conversation="User: hi\nAI: hello")
        assert "4" in result
        assert "User: hi" in result


# ---------------------------------------------------------------------------
# Integration tests (real LLM, no mock)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("LITE_API_KEY"),
    reason="LITE_API_KEY not configured for integration tests",
)
class TestExtractCorrectionSummaryIntegration:
    """Integration tests for _extract_correction_summary with real LLM."""

    @pytest.mark.asyncio
    async def test_extracts_correction_from_english_conversation(
        self, lite_llm_func: Any, correction_messages: list[dict[str, str]]
    ) -> None:
        from app.ai_agents.general_agent.callbacks import _extract_correction_summary

        result = await _extract_correction_summary(correction_messages, lite_llm_func)
        assert result, "Should extract a non-empty correction summary"
        assert len(result) > 5, "Summary should be meaningful"
        lower = result.lower()
        assert "mindforge" in lower or "mindforce" in lower, f"Summary should mention the corrected entity, got: {result}"

    @pytest.mark.asyncio
    async def test_extracts_correction_from_chinese_conversation(
        self, lite_llm_func: Any, zh_correction_messages: list[dict[str, str]]
    ) -> None:
        from app.ai_agents.general_agent.callbacks import _extract_correction_summary

        result = await _extract_correction_summary(zh_correction_messages, lite_llm_func)
        assert result, "Should extract a non-empty correction summary"
        assert len(result) > 5
        assert "mindforge" in result.lower() or "mindforce" in result.lower() or "MindForge" in result, (
            f"Summary should mention the corrected entity, got: {result}"
        )

    @pytest.mark.asyncio
    async def test_returns_empty_for_normal_conversation(
        self, lite_llm_func: Any, no_correction_messages: list[dict[str, str]]
    ) -> None:
        from app.ai_agents.general_agent.callbacks import _extract_correction_summary

        result = await _extract_correction_summary(no_correction_messages, lite_llm_func)
        assert len(result) < 200, f"Should be short or empty, got: {result}"

    @pytest.mark.asyncio
    async def test_handles_long_messages_truncation(self, lite_llm_func: Any) -> None:
        """Verify that very long messages are properly truncated."""
        from app.ai_agents.general_agent.callbacks import _extract_correction_summary

        messages = [
            {"role": "user", "content": "A" * 2000},
            {"role": "assistant", "content": "B" * 2000},
            {"role": "user", "content": "That's wrong! The correct answer is C."},
            {"role": "assistant", "content": "Sorry, C it is."},
        ]
        result = await _extract_correction_summary(messages, lite_llm_func)
        assert len(result) <= 1000, "Result should be truncated to 1000 chars"


@pytest.mark.skipif(
    not os.getenv("LITE_API_KEY"),
    reason="LITE_API_KEY not configured for integration tests",
)
class TestCorrectionPropagationEndToEnd:
    """End-to-end test: correction detection → summary extraction."""

    @pytest.mark.asyncio
    async def test_full_pipeline_with_correction(self, lite_llm_func: Any, correction_messages: list[dict[str, str]]) -> None:
        """Verify the full pipeline from detection to summary extraction."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        from app.ai_agents.general_agent.callbacks import _extract_correction_summary

        signal = detect_feedback_signals(correction_messages)
        assert signal == FeedbackSignal.NEGATIVE, "Should detect correction"

        summary = await _extract_correction_summary(correction_messages, lite_llm_func)
        assert summary, "Should produce non-empty summary"
        assert len(summary) > 5
        print(f"\nExtracted correction summary: {summary}")

    def test_full_pipeline_without_correction(self, no_correction_messages: list[dict[str, str]]) -> None:
        """Verify the pipeline short-circuits when no correction is detected."""
        from myrm_agent_harness.toolkits.memory.strategies.extractor import (
            FeedbackSignal,
            detect_feedback_signals,
        )

        signal = detect_feedback_signals(no_correction_messages)
        assert signal != FeedbackSignal.NEGATIVE, "Should NOT detect correction"
