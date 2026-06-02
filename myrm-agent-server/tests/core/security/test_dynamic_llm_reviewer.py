"""Unit tests for DynamicLLMSecurityReviewer.

Validates:
- Correct parameter forwarding to TranscriptClassifier (especially trusted_domains)
- Graceful fallback to UNCERTAIN on LLM initialization errors
- Warning log when no model_id is specified
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security.types import (
    RecentToolCall,
    ReviewDecision,
    ReviewResult,
)

from app.core.security.llm_reviewer import DynamicLLMSecurityReviewer


@pytest.fixture
def reviewer() -> DynamicLLMSecurityReviewer:
    return DynamicLLMSecurityReviewer(timeout_seconds=2.0)


class TestParameterForwarding:
    """Ensure all parameters are correctly forwarded to TranscriptClassifier."""

    @pytest.mark.asyncio
    async def test_trusted_domains_forwarded(self, reviewer: DynamicLLMSecurityReviewer):
        mock_llm = MagicMock()
        expected_result = ReviewResult(
            decision=ReviewDecision.ALLOW, reason="safe"
        )

        with (
            patch(
                "app.core.security.llm_reviewer.get_llm_for_user",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "app.core.security.llm_reviewer.TranscriptClassifier"
            ) as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_instance.review = AsyncMock(return_value=expected_result)
            mock_cls.return_value = mock_instance

            result = await reviewer.review(
                "curl https://internal.api.com/data",
                workspace_root="/home/user/project",
                intent_context="Download API schema",
                taint_labels=frozenset({"network"}),
                recent_tool_calls=(
                    RecentToolCall(tool_name="bash", args="ls"),
                ),
                model_id="gpt-4o",
                trusted_domains=("api.github.com", "internal.api.com"),
            )

            mock_instance.review.assert_called_once_with(
                "curl https://internal.api.com/data",
                workspace_root="/home/user/project",
                intent_context="Download API schema",
                taint_labels=frozenset({"network"}),
                recent_tool_calls=(
                    RecentToolCall(tool_name="bash", args="ls"),
                ),
                model_id="gpt-4o",
                trusted_domains=("api.github.com", "internal.api.com"),
            )
            assert result == expected_result

    @pytest.mark.asyncio
    async def test_empty_trusted_domains_default(self, reviewer: DynamicLLMSecurityReviewer):
        mock_llm = MagicMock()
        expected_result = ReviewResult(
            decision=ReviewDecision.DENY, reason="dangerous"
        )

        with (
            patch(
                "app.core.security.llm_reviewer.get_llm_for_user",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "app.core.security.llm_reviewer.TranscriptClassifier"
            ) as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_instance.review = AsyncMock(return_value=expected_result)
            mock_cls.return_value = mock_instance

            result = await reviewer.review("rm -rf /", model_id="gpt-4o")

            call_kwargs = mock_instance.review.call_args.kwargs
            assert call_kwargs["trusted_domains"] == ()
            assert result.decision == ReviewDecision.DENY


class TestErrorHandling:
    """Ensure graceful degradation when LLM is unavailable."""

    @pytest.mark.asyncio
    async def test_llm_init_failure_returns_uncertain(self, reviewer: DynamicLLMSecurityReviewer):
        with patch(
            "app.core.security.llm_reviewer.get_llm_for_user",
            new_callable=AsyncMock,
            side_effect=RuntimeError("No API key configured"),
        ):
            result = await reviewer.review(
                "some command",
                model_id="invalid-model",
                trusted_domains=("example.com",),
            )

            assert result.decision == ReviewDecision.UNCERTAIN
            assert "LLM initialization error" in result.reason

    @pytest.mark.asyncio
    async def test_classifier_review_exception_returns_uncertain(
        self, reviewer: DynamicLLMSecurityReviewer
    ):
        mock_llm = MagicMock()

        with (
            patch(
                "app.core.security.llm_reviewer.get_llm_for_user",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "app.core.security.llm_reviewer.TranscriptClassifier"
            ) as mock_cls,
        ):
            mock_instance = MagicMock()
            mock_instance.review = AsyncMock(
                side_effect=TimeoutError("LLM timeout")
            )
            mock_cls.return_value = mock_instance

            result = await reviewer.review("test", model_id="gpt-4o")

            assert result.decision == ReviewDecision.UNCERTAIN


class TestWarningLogs:
    """Validate appropriate warning logs."""

    @pytest.mark.asyncio
    async def test_no_model_id_logs_warning(self, reviewer: DynamicLLMSecurityReviewer):
        mock_llm = MagicMock()
        expected_result = ReviewResult(
            decision=ReviewDecision.ALLOW, reason="ok"
        )

        with (
            patch(
                "app.core.security.llm_reviewer.get_llm_for_user",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "app.core.security.llm_reviewer.TranscriptClassifier"
            ) as mock_cls,
            patch(
                "app.core.security.llm_reviewer.logger"
            ) as mock_logger,
        ):
            mock_instance = MagicMock()
            mock_instance.review = AsyncMock(return_value=expected_result)
            mock_cls.return_value = mock_instance

            await reviewer.review("test command", model_id=None)

            mock_logger.warning.assert_called_once()
            warning_msg = mock_logger.warning.call_args[0][0]
            assert "default model" in warning_msg

    @pytest.mark.asyncio
    async def test_with_model_id_no_warning(self, reviewer: DynamicLLMSecurityReviewer):
        mock_llm = MagicMock()
        expected_result = ReviewResult(
            decision=ReviewDecision.ALLOW, reason="ok"
        )

        with (
            patch(
                "app.core.security.llm_reviewer.get_llm_for_user",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
            patch(
                "app.core.security.llm_reviewer.TranscriptClassifier"
            ) as mock_cls,
            patch(
                "app.core.security.llm_reviewer.logger"
            ) as mock_logger,
        ):
            mock_instance = MagicMock()
            mock_instance.review = AsyncMock(return_value=expected_result)
            mock_cls.return_value = mock_instance

            await reviewer.review("test command", model_id="gpt-4o")

            mock_logger.warning.assert_not_called()
