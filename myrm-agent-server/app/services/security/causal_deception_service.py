"""Causal Deception Defense & Mechanism Probe Service.

[INPUT]
- AuditCausalConsistencyRequest, AudienceProbeRequest.

[OUTPUT]
- AuditCausalConsistencyResponse, AudienceProbeResponse.

[POS]
- Server security service. Wraps harness CausalConsistencyGuard to enforce
  three-way commitment-execution-report invariance and counterfactual audience probes.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.causal_deception import (
    CausalConsistencyGuard,
    ClaimStatus,
    CommitmentItem,
    CommitmentType,
    ExecutionTraceItem,
    PostReportClaim,
    TechnicalProficiency,
)

from app.schemas.causal_deception import (
    AudienceProbeRequest,
    AudienceProbeResponse,
    AuditCausalConsistencyRequest,
    AuditCausalConsistencyResponse,
    CommitmentItemDto,
    ExecutionTraceItemDto,
    InvarianceViolationDto,
    PostReportClaimDto,
)

logger = logging.getLogger(__name__)


def _to_domain_commitment(dto: CommitmentItemDto) -> CommitmentItem:
    return CommitmentItem(
        commitment_id=dto.commitment_id,
        commitment_type=CommitmentType(dto.commitment_type),
        target_subject=dto.target_subject,
        description=dto.description,
    )


def _to_domain_trace(dto: ExecutionTraceItemDto) -> ExecutionTraceItem:
    return ExecutionTraceItem(
        trace_id=dto.trace_id,
        tool_name=dto.tool_name,
        arguments=dto.arguments,
        output_summary=dto.output_summary,
        is_success=dto.is_success,
        timestamp=dto.timestamp,
    )


def _to_domain_claim(dto: PostReportClaimDto) -> PostReportClaim:
    return PostReportClaim(
        claim_id=dto.claim_id,
        commitment_type=CommitmentType(dto.commitment_type),
        claimed_status=ClaimStatus(dto.claimed_status),
        target_subject=dto.target_subject,
        assertion_text=dto.assertion_text,
    )


class CausalDeceptionService:
    """Service auditing agent reports against objective physical tool traces."""

    def __init__(self) -> None:
        self._guard = CausalConsistencyGuard()

    @property
    def guard(self) -> CausalConsistencyGuard:
        """Underlying harness guard."""
        return self._guard

    def audit_consistency(
        self, req: AuditCausalConsistencyRequest
    ) -> AuditCausalConsistencyResponse:
        """Evaluate three-way consistency between commitments, physical traces, and claims."""
        guard = CausalConsistencyGuard()

        for comm in req.commitments:
            guard.record_commitment(_to_domain_commitment(comm))

        for tr in req.traces:
            guard.record_execution_trace(_to_domain_trace(tr))

        for cl in req.claims:
            guard.record_claim(_to_domain_claim(cl))

        report = guard.audit_consistency()

        violations = [
            InvarianceViolationDto(
                claim_id=v.claim_id,
                verdict=v.verdict.value,
                reason=v.reason,
                target_subject=v.target_subject,
            )
            for v in report.violations
        ]

        return AuditCausalConsistencyResponse(
            is_consistent=report.is_consistent,
            overall_verdict=report.overall_verdict.value,
            total_commitments=report.total_commitments,
            total_traces=report.total_traces,
            total_claims=report.total_claims,
            risk_score=report.risk_score,
            violations=violations,
        )

    def probe_audience(self, req: AudienceProbeRequest) -> AudienceProbeResponse:
        """Run counterfactual probe evaluating whether report exploits novice audience vulnerabilities."""
        guard = CausalConsistencyGuard()

        for tr in req.traces:
            guard.record_execution_trace(_to_domain_trace(tr))

        domain_claims = [_to_domain_claim(cl) for cl in req.claims]
        for cl in domain_claims:
            guard.record_claim(cl)

        audience_tier = TechnicalProficiency(req.audience_level)
        probe_res = guard.probe_audience(
            claims=domain_claims,
            audience_level=audience_tier,
        )

        return AudienceProbeResponse(
            probe_id=probe_res.probe_id,
            baseline_audience=probe_res.baseline_audience.value,
            adversarial_audience=probe_res.adversarial_audience.value,
            is_asymmetric_deception=probe_res.is_asymmetric_deception,
            discrepancy_details=probe_res.discrepancy_details,
            vulnerability_index=probe_res.vulnerability_index,
        )


_service_instance: CausalDeceptionService | None = None


def get_causal_deception_service() -> CausalDeceptionService:
    """Obtain or initialize the singleton CausalDeceptionService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CausalDeceptionService()
    return _service_instance
