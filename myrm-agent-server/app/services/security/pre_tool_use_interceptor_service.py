"""Service layer for PreToolUse Hook Interceptor & API Key Precedence.

[INPUT]
- Pydantic DTO requests from API endpoints and tool dispatch wrappers.

[OUTPUT]
- Deterministic verdicts, security rejections, and ambient API key conflict warnings.

[POS]
- Bridge between FastAPI routes and Harness PreToolUseHookInterceptor.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.pre_tool_use_interceptor import (
    ApiKeyPrecedenceCheckResult,
    ApiKeyPrecedenceDetector,
    HardGateSecurityRejectionError,
    PreToolUseHookInterceptor,
    PreToolUseInterceptResult,
)

from app.schemas.pre_tool_use_interceptor import (
    DetectApiKeyConflictRequest,
    DetectApiKeyConflictResponse,
    HardRuleSpecDto,
    InterceptToolUseRequest,
    InterceptToolUseResponse,
)

logger = logging.getLogger(__name__)


class PreToolUseInterceptorService:
    """Service governing pre-tool execution deterministic gates and billing route safety."""

    def __init__(
        self,
        interceptor: PreToolUseHookInterceptor | None = None,
    ) -> None:
        """Initialize service with interceptor instance."""
        self._interceptor = interceptor or PreToolUseHookInterceptor()

    def intercept_tool(
        self, request: InterceptToolUseRequest
    ) -> InterceptToolUseResponse:
        """Inspect proposed tool execution payload against non-negotiable hard rules."""
        try:
            result: PreToolUseInterceptResult = self._interceptor.intercept(
                tool_name=request.tool_name,
                payload_str=request.payload_str,
                raise_on_block=request.raise_on_block,
            )
        except HardGateSecurityRejectionError as err:
            logger.warning(
                "Tool execution blocked by hard gate: %s (tool=%s)",
                err,
                request.tool_name,
            )
            raise

        if result.verdict.value == "BLOCK":
            logger.warning(
                "Pre-tool use block: %s on tool '%s'",
                result.rejection_reason,
                request.tool_name,
            )

        return InterceptToolUseResponse(
            verdict=result.verdict.value,
            blocked_rule_id=result.blocked_rule_id,
            rule_category=(
                result.rule_category.value if result.rule_category else None
            ),
            rejection_reason=result.rejection_reason,
            detected_pattern=result.detected_pattern,
        )

    def detect_key_conflicts(
        self, request: DetectApiKeyConflictRequest
    ) -> DetectApiKeyConflictResponse:
        """Analyze environment variables to prevent silent per-token billing surcharges."""
        result: ApiKeyPrecedenceCheckResult = (
            ApiKeyPrecedenceDetector.detect_conflicts(
                active_provider=request.active_provider,
                is_subscription_route=request.is_subscription_route,
                env_dict=request.env_dict,
            )
        )
        if result.has_conflict:
            logger.warning(
                "Billing precedence conflict detected: %s",
                result.warning_message,
            )

        return DetectApiKeyConflictResponse(
            has_conflict=result.has_conflict,
            detected_env_vars=result.detected_env_vars,
            active_provider=result.active_provider,
            warning_message=result.warning_message,
            recommended_action=result.recommended_action,
        )

    def get_rules(self) -> list[HardRuleSpecDto]:
        """Return list of active hard invariant rules."""
        rules = self._interceptor.get_rules()
        return [
            HardRuleSpecDto(
                rule_id=r.rule_id,
                category=r.category.value,
                pattern=r.pattern,
                description=r.description,
                enabled=r.enabled,
            )
            for r in rules
        ]

    def toggle_rule(self, rule_id: str, enabled: bool) -> bool:
        """Enable or disable a hard invariant rule."""
        return self._interceptor.set_rule_enabled(rule_id, enabled)


_service_instance: PreToolUseInterceptorService | None = None


def get_pre_tool_use_interceptor_service() -> PreToolUseInterceptorService:
    """Dependency injector for PreToolUseInterceptorService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PreToolUseInterceptorService()
    return _service_instance
