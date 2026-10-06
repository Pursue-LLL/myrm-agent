"""Service implementation for CoS Sensitive OTP Isolation, Recovery Blackhole, and JIT Authorization.

[POS] app/services/security/cos_otp_isolation_jit_service.py
[INPUT] myrm_agent_harness.core.security.cos_otp_isolation_jit, app.schemas.cos_otp_isolation_jit
[OUTPUT] CosOtpIsolationJitService, get_cos_otp_isolation_jit_service
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.cos_otp_isolation_jit.jit_gate import (
    IntentBoundJitAuthorizationGate,
)
from myrm_agent_harness.core.security.cos_otp_isolation_jit.otp_redactor import (
    SensitiveOtpRedactor,
)
from myrm_agent_harness.core.security.cos_otp_isolation_jit.quota_rails import (
    QuotaWatermarkGuard,
)

from app.schemas.cos_otp_isolation_jit import (
    BlackholeCheckRequest,
    BlackholeCheckResponse,
    ConsumeJitTicketRequest,
    ConsumeJitTicketResponse,
    EvaluateQuotaRequest,
    EvaluateQuotaResponse,
    InspectMessageOtpRequest,
    InspectMessageOtpResponse,
    IssueJitTicketRequest,
    JitTicketResponse,
)

logger = logging.getLogger(__name__)


class CosOtpIsolationJitService:
    """Business service governing dynamic OTP redaction, recovery link blackhole, and intent-bound JIT tickets."""

    def __init__(
        self,
        redactor: SensitiveOtpRedactor | None = None,
        jit_gate: IntentBoundJitAuthorizationGate | None = None,
        quota_guard: QuotaWatermarkGuard | None = None,
    ) -> None:
        self._redactor = redactor or SensitiveOtpRedactor()
        self._jit_gate = jit_gate or IntentBoundJitAuthorizationGate()
        self._quota_guard = quota_guard or QuotaWatermarkGuard()

    def inspect_message_otps(self, req: InspectMessageOtpRequest) -> InspectMessageOtpResponse:
        """Dynamically redact OTP codes from messaging streams before LLM context injection."""
        result = self._redactor.redact_otps(req.message_text)
        return InspectMessageOtpResponse(
            original_text=result.original_text,
            sanitized_text=result.sanitized_text,
            detected_otp_codes=result.detected_otp_codes,
            redaction_count=result.redaction_count,
            contains_password_reset_link=result.contains_password_reset_link,
        )

    def check_recovery_blackhole(self, req: BlackholeCheckRequest) -> BlackholeCheckResponse:
        """Inspect targets against password reset and account recovery blackhole rules."""
        result = self._redactor.inspect_recovery_blackhole(req.target_text_or_url)
        return BlackholeCheckResponse(
            is_blackholed=result.is_blackholed,
            detected_links=result.detected_links,
            reason=result.reason,
            human_intervention_required=result.human_intervention_required,
        )

    def issue_jit_ticket(self, req: IssueJitTicketRequest) -> JitTicketResponse:
        """Issue an ephemeral, intent-bound JIT authorization ticket for single-use injection."""
        ticket = self._jit_gate.issue_ticket(
            session_id=req.session_id,
            target_domain=req.target_domain,
            purpose=req.purpose,
            otp_code=req.otp_code,
            validity_seconds=req.validity_seconds,
        )
        return JitTicketResponse(
            ticket_id=ticket.ticket_id,
            session_id=ticket.session_id,
            target_domain=ticket.target_domain,
            purpose=ticket.purpose,
            issued_at=ticket.issued_at,
            expires_at=ticket.expires_at,
            consumed=ticket.consumed,
        )

    def consume_jit_ticket(self, req: ConsumeJitTicketRequest) -> ConsumeJitTicketResponse:
        """Consume a JIT ticket using burn-after-reading semantics."""
        raw_code = self._jit_gate.consume_ticket(
            ticket_id=req.ticket_id,
            target_domain=req.target_domain,
        )
        if raw_code is not None:
            return ConsumeJitTicketResponse(
                success=True,
                otp_code=raw_code,
                reason="Ticket consumed successfully and burned after reading.",
            )
        return ConsumeJitTicketResponse(
            success=False,
            otp_code=None,
            reason="Ticket invalid, expired, domain mismatched, or already burned.",
        )

    def evaluate_quota(self, req: EvaluateQuotaRequest) -> EvaluateQuotaResponse:
        """Evaluate quota usage and return watermark alerts with fallback guidance."""
        assessment = self._quota_guard.assess_quota(
            used_units=req.used_units,
            max_units=req.max_units,
            fallback_model=req.fallback_model,
        )
        return EvaluateQuotaResponse(
            used_units=assessment.used_units,
            max_units=assessment.max_units,
            usage_ratio=assessment.usage_ratio,
            tier=assessment.tier.value,
            alert_message=assessment.alert_message,
            fallback_model_recommended=assessment.fallback_model_recommended,
        )


_service_instance: CosOtpIsolationJitService | None = None


def get_cos_otp_isolation_jit_service() -> CosOtpIsolationJitService:
    """Singleton getter for CosOtpIsolationJitService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CosOtpIsolationJitService()
    return _service_instance
