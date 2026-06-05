"""Dynamic LLM security reviewer for the server layer.

[INPUT]
- myrm_agent_harness.agent.security.types::ReviewResult, SecurityReviewerProtocol, RecentToolCall
- app.api.dependencies::get_llm_for_user

[OUTPUT]
- DynamicLLMSecurityReviewer: Server-layer implementation of SecurityReviewerProtocol

[POS]
Server-layer security reviewer that dynamically fetches the user's latest LLM
configuration for each review request, rather than binding to a static model.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.security.transcript_classifier import (
    TranscriptClassifier,
)
from myrm_agent_harness.agent.security.types import (
    RecentToolCall,
    ReviewResult,
    SecurityReviewerProtocol,
)

from app.api.dependencies import get_llm_for_user

logger = logging.getLogger(__name__)


class DynamicLLMSecurityReviewer(SecurityReviewerProtocol):
    """Server-layer security reviewer that fetches the LLM dynamically."""

    def __init__(self, timeout_seconds: float = 3.0) -> None:
        self._timeout = timeout_seconds

    async def review(
        self,
        command: str,
        *,
        workspace_root: str | None = None,
        intent_context: str | None = None,
        taint_labels: frozenset[str] | None = None,
        recent_tool_calls: tuple[RecentToolCall, ...] = (),
        model_id: str | None = None,
        trusted_domains: tuple[str, ...] = (),
    ) -> ReviewResult:
        try:
            if not model_id:
                logger.warning(
                    "Transcript classifier running with user's default model "
                    "(no auto_review_model configured). "
                    "Consider selecting a dedicated reviewer model for consistent security quality."
                )
            llm = await get_llm_for_user(model_id=model_id)

            classifier = TranscriptClassifier(llm=llm, timeout_seconds=self._timeout)
            return await classifier.review(
                command,
                workspace_root=workspace_root,
                intent_context=intent_context,
                taint_labels=taint_labels,
                recent_tool_calls=recent_tool_calls,
                model_id=model_id,
                trusted_domains=trusted_domains,
            )
        except Exception as e:
            logger.warning("Dynamic transcript classifier failed to initialize LLM: %s", e)
            from myrm_agent_harness.agent.security.types import ReviewDecision

            return ReviewResult(
                decision=ReviewDecision.UNCERTAIN,
                reason="LLM initialization error",
            )
