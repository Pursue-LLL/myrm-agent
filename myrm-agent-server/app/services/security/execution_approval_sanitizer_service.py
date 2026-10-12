"""
[POS] app/services/security/execution_approval_sanitizer_service.py
[INPUT] app.schemas.execution_approval_sanitizer, myrm_agent_harness.core.security.execution_approval_sanitizer
[OUTPUT] ExecutionApprovalSanitizerService, get_execution_approval_sanitizer_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.execution_approval_sanitizer import (
    ApprovalPayloadRequest,
    ExecutionApprovalSanitizerFacade,
)

from app.schemas.execution_approval_sanitizer import (
    ApprovalSanitizeRequestDTO,
    ApprovalSanitizeResponseDTO,
    QuickSanitizeRequestDTO,
    QuickSanitizeResponseDTO,
    RedactionFindingDTO,
    SanitizerMetricsResponseDTO,
)

logger = logging.getLogger(__name__)


class ExecutionApprovalSanitizerService:
    """Service mediating presentation-layer secret redaction for execution approval commands."""

    def __init__(
        self, facade: ExecutionApprovalSanitizerFacade | None = None
    ) -> None:
        self._facade = facade or ExecutionApprovalSanitizerFacade()

    def sanitize_approval_payload(
        self, request: ApprovalSanitizeRequestDTO
    ) -> ApprovalSanitizeResponseDTO:
        """Scan and mask recognizable API keys, tokens, and credentials in approval command."""
        req_domain = ApprovalPayloadRequest(
            request_id=request.request_id,
            session_id=request.session_id,
            raw_command_or_text=request.raw_command_or_text,
            channel_target=request.channel_target,
            metadata=request.metadata,
        )
        res = self._facade.sanitize_payload(req_domain)

        findings_dtos = [
            RedactionFindingDTO(
                secret_type=f.secret_type.value,
                start_index=f.start_index,
                end_index=f.end_index,
                matched_preview=f.matched_preview,
                placeholder=f.placeholder,
            )
            for f in res.findings
        ]

        return ApprovalSanitizeResponseDTO(
            request_id=request.request_id,
            session_id=request.session_id,
            sanitized_text=res.sanitized_text,
            redactions_count=res.redactions_count,
            detected_secret_types=[t.value for t in res.detected_secret_types],
            findings=findings_dtos,
            badge_summary=res.badge_summary,
        )

    def quick_sanitize_text(
        self, request: QuickSanitizeRequestDTO
    ) -> QuickSanitizeResponseDTO:
        """Sanitize raw text directly without session envelope."""
        res = self._facade.sanitize_raw_text(request.text)
        return QuickSanitizeResponseDTO(
            sanitized_text=res.sanitized_text,
            redactions_count=res.redactions_count,
            detected_secret_types=[t.value for t in res.detected_secret_types],
            badge_summary=res.badge_summary,
        )

    def get_metrics(self) -> SanitizerMetricsResponseDTO:
        """Retrieve operational metric counters."""
        m = self._facade.metrics
        return SanitizerMetricsResponseDTO(
            payloads_evaluated_total=m.payloads_evaluated_total,
            clean_payloads_total=m.clean_payloads_total,
            redacted_payloads_total=m.redacted_payloads_total,
            total_secrets_redacted_count=m.total_secrets_redacted_count,
        )


_global_service: ExecutionApprovalSanitizerService | None = None


def get_execution_approval_sanitizer_service() -> ExecutionApprovalSanitizerService:
    """Singleton provider for ExecutionApprovalSanitizerService."""
    global _global_service
    if _global_service is None:
        _global_service = ExecutionApprovalSanitizerService()
    return _global_service
