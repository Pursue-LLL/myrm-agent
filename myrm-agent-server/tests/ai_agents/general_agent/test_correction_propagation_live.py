"""Implicit feedback detection and correction planning against the real LLM named by LITE_MODEL.

Skipped without LITE_API_KEY.
"""

import os
from collections.abc import AsyncIterator

import pytest
from dotenv import load_dotenv
from myrm_agent_harness.toolkits.memory.strategies.extractor import LLMFunc

from tests.support.live_chat_model import live_chat_model

load_dotenv(override=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
async def lite_llm_func() -> AsyncIterator[LLMFunc]:
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

    async with live_chat_model(model=model, api_key=api_key, base_url=base_url, temperature=0, max_tokens=512, timeout=60) as llm:
        yield create_extraction_llm_func(llm)


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
        self, lite_llm_func: LLMFunc, correction_messages: list[dict[str, str]]
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
        self, lite_llm_func: LLMFunc, implicit_correction_messages: list[dict[str, str]]
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
        self, lite_llm_func: LLMFunc, no_correction_messages: list[dict[str, str]]
    ) -> None:
        from myrm_agent_harness.toolkits.memory.strategies.extractor import FeedbackSignal
        from myrm_agent_harness.toolkits.memory.strategies.implicit_feedback import (
            detect_implicit_feedback,
        )

        result = await detect_implicit_feedback(no_correction_messages, lite_llm_func)
        assert result.signal != FeedbackSignal.NEGATIVE

    @pytest.mark.asyncio
    async def test_chinese_correction_plans(self, lite_llm_func: LLMFunc, zh_correction_messages: list[dict[str, str]]) -> None:
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
    async def test_full_pipeline_with_correction(self, lite_llm_func: LLMFunc, correction_messages: list[dict[str, str]]) -> None:
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
