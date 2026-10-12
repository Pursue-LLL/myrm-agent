"""Service layer for GateGuard invisible Unicode sanitization.

[INPUT]
- SanitizePathRequest, SanitizeReasonRequest, or SanitizeDenialPayloadRequest DTOs.

[OUTPUT]
- Cleaned and verified DTO responses with detected categories and audit metrics.

[POS]
- Server service layer providing gate guard denial path Unicode sanitization.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.gate_guard_sanitizer import (
    DenialSanitizePolicy,
    GateGuardDenialSanitizer,
    InvisibleUnicodeCategory,
    SanitizeResult,
)

from app.schemas.gate_guard_sanitizer import (
    GateGuardSanitizePolicySummary,
    SanitizeDenialPayloadRequest,
    SanitizeDenialPayloadResponse,
    SanitizePathRequest,
    SanitizeReasonRequest,
    SanitizeResultDto,
)

logger = logging.getLogger(__name__)


def _to_dto(res: SanitizeResult) -> SanitizeResultDto:
    """Convert harness SanitizeResult to server DTO."""
    return SanitizeResultDto(
        original_text=res.original_text,
        sanitized_text=res.sanitized_text,
        characters_removed_count=res.characters_removed_count,
        categories_detected=[c.value for c in res.categories_detected],
        was_truncated=res.was_truncated,
        has_modifications=res.has_modifications,
    )


class GateGuardSanitizerService:
    """Service wrapping GateGuard invisible Unicode sanitization."""

    def __init__(self, policy: DenialSanitizePolicy | None = None) -> None:
        self._policy = policy or DenialSanitizePolicy()
        self._sanitizer = GateGuardDenialSanitizer(self._policy)

    def sanitize_path(self, req: SanitizePathRequest) -> SanitizeResultDto:
        """Sanitize an untrusted path for denial output."""
        res = self._sanitizer.sanitize_path(req.path, max_length=req.max_length)
        if res.has_modifications:
            logger.warning(
                "GateGuard sanitized dangerous Unicode in denial path: removed=%d, categories=%s",
                res.characters_removed_count,
                [c.value for c in res.categories_detected],
            )
        return _to_dto(res)

    def sanitize_reason(self, req: SanitizeReasonRequest) -> SanitizeResultDto:
        """Sanitize an untrusted denial reason string."""
        res = self._sanitizer.sanitize_reason(req.reason, max_length=req.max_length)
        if res.has_modifications:
            logger.warning(
                "GateGuard sanitized dangerous Unicode in denial reason: removed=%d, categories=%s",
                res.characters_removed_count,
                [c.value for c in res.categories_detected],
            )
        return _to_dto(res)

    def sanitize_denial_payload(
        self, req: SanitizeDenialPayloadRequest
    ) -> SanitizeDenialPayloadResponse:
        """Sanitize a full denial event payload."""
        tool_res = self._sanitizer.sanitize_text(req.tool_name, max_length=100)
        reason_res = self._sanitizer.sanitize_reason(req.reason)
        path_res = (
            self._sanitizer.sanitize_path(req.target_path)
            if req.target_path is not None
            else None
        )

        has_mod = (
            tool_res.has_modifications
            or reason_res.has_modifications
            or (path_res.has_modifications if path_res is not None else False)
        )

        return SanitizeDenialPayloadResponse(
            tool_name=tool_res.sanitized_text,
            target_path=path_res.sanitized_text if path_res is not None else None,
            reason=reason_res.sanitized_text,
            has_modifications=has_mod,
        )

    def get_policy_summary(self) -> GateGuardSanitizePolicySummary:
        """Return the active GateGuard sanitization policy configuration."""
        return GateGuardSanitizePolicySummary(
            replacement_char=self._policy.replacement_char,
            max_path_length=self._policy.max_path_length,
            max_reason_length=self._policy.max_reason_length,
            supported_categories=[c.value for c in InvisibleUnicodeCategory],
        )


_instance: GateGuardSanitizerService | None = None


def get_gate_guard_sanitizer_service() -> GateGuardSanitizerService:
    """FastAPI dependency provider for GateGuardSanitizerService."""
    global _instance
    if _instance is None:
        _instance = GateGuardSanitizerService()
    return _instance
