"""Business service implementing Thinking Block Sanitizer & Prompt Contamination Shield (Item 115).

[POS]
app/services/memory/thinking_sanitizer_service.py

[INPUT]
- app.schemas.thinking_sanitizer, myrm_agent_harness.toolkits.memory

[OUTPUT]
- ThinkingSanitizerService, get_thinking_sanitizer_service
"""


from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    SanitizationResult,
    ThinkingBlockSanitizer,
    ThinkingSanitizerConfig,
)

from app.schemas.thinking_sanitizer import (
    SanitizationResultDTO,
    ThinkingSanitizerConfigDTO,
    UsableSummaryCheckResponse,
)

logger = logging.getLogger(__name__)


def _result_to_dto(result: SanitizationResult) -> SanitizationResultDTO:
    """Map internal SanitizationResult domain model to API DTO."""
    return SanitizationResultDTO(
        original_text=result.original_text,
        cleaned_text=result.cleaned_text,
        has_thinking_markers=result.has_thinking_markers,
        has_unclosed_tags=result.has_unclosed_tags,
        stripped_markers_count=result.stripped_markers_count,
        is_usable=result.is_usable,
        rejection_reason=result.rejection_reason,
    )


def _dto_to_config(dto: ThinkingSanitizerConfigDTO | None) -> ThinkingSanitizerConfig:
    """Map optional configuration DTO to internal domain configuration."""
    if dto is None:
        return ThinkingSanitizerConfig()
    return ThinkingSanitizerConfig(
        min_usable_chars=dto.min_usable_chars,
        strip_planning_leadins=dto.strip_planning_leadins,
        preserve_post_close_text=dto.preserve_post_close_text,
        drop_unclosed_tags=dto.drop_unclosed_tags,
        extra_planning_patterns=tuple(dto.extra_planning_patterns),
    )


class ThinkingSanitizerService:
    """Domain service orchestrating thinking channel scrubbing and egress guards."""

    def __init__(self, default_sanitizer: ThinkingBlockSanitizer | None = None) -> None:
        self._default_sanitizer = default_sanitizer or ThinkingBlockSanitizer()

    def sanitize(
        self,
        text: str,
        config: ThinkingSanitizerConfigDTO | None = None,
    ) -> SanitizationResultDTO:
        """Sanitize reasoning tags, orphan endings, and planning lead-ins from text."""
        sanitizer = (
            ThinkingBlockSanitizer(_dto_to_config(config))
            if config is not None
            else self._default_sanitizer
        )
        result = sanitizer.sanitize(text)
        return _result_to_dto(result)

    def check_usable_summary(
        self,
        text: str,
        config: ThinkingSanitizerConfigDTO | None = None,
    ) -> UsableSummaryCheckResponse:
        """Evaluate whether candidate summary satisfies egress safety guards for prompt injection."""
        sanitizer = (
            ThinkingBlockSanitizer(_dto_to_config(config))
            if config is not None
            else self._default_sanitizer
        )
        usable_summary = sanitizer.is_usable_summary(text)
        if usable_summary is not None:
            return UsableSummaryCheckResponse(
                is_usable=True,
                summary=usable_summary,
                rejection_reason=None,
            )

        sanitized = sanitizer.sanitize(text)
        return UsableSummaryCheckResponse(
            is_usable=False,
            summary=None,
            rejection_reason=sanitized.rejection_reason or "Summary omitted by egress guard",
        )


@lru_cache(maxsize=1)
def get_thinking_sanitizer_service() -> ThinkingSanitizerService:
    """Return the singleton instance of ThinkingSanitizerService."""
    return ThinkingSanitizerService()
