"""
[POS] app/services/security/scoped_approval_gate_service.py
[INPUT] app.schemas.scoped_approval_gate, myrm_agent_harness.core.security.scoped_approval
[OUTPUT] ScopedApprovalGateService, get_scoped_approval_gate_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.scoped_approval import (
    ActionRiskTier,
    ApprovalGrantLease,
    GrantScope,
    GrantUsageRecord,
    RiskEvaluationRequest,
    ScopedApprovalGateFacade,
)

from app.schemas.scoped_approval_gate import (
    ApprovalGrantLeaseDTO,
    AuditLedgerResponseDTO,
    GrantUsageRecordDTO,
    IssueGrantRequestDTO,
    ListActiveGrantsResponseDTO,
    RevokeAllRequestDTO,
    RevokeAllResponseDTO,
    RevokeGrantResponseDTO,
    RiskEvaluationRequestDTO,
    RiskEvaluationResultDTO,
    ScopedApprovalMetricsDTO,
)

logger = logging.getLogger(__name__)


class ScopedApprovalGateService:
    """Service mediating scoped permission grants, tiered gate evaluations, and audit ledgers."""

    def __init__(self, facade: ScopedApprovalGateFacade | None = None) -> None:
        self._facade = facade or ScopedApprovalGateFacade()

    @staticmethod
    def _to_lease_dto(lease: ApprovalGrantLease) -> ApprovalGrantLeaseDTO:
        return ApprovalGrantLeaseDTO(
            grant_id=lease.grant_id,
            tool_name=lease.tool_name,
            scope=lease.scope.value,
            agent_id=lease.agent_id,
            session_id=lease.session_id,
            task_id=lease.task_id,
            granted_at=lease.granted_at,
            expires_at=lease.expires_at,
            revoked=lease.revoked,
            use_count=lease.use_count,
        )

    @staticmethod
    def _to_record_dto(record: GrantUsageRecord) -> GrantUsageRecordDTO:
        return GrantUsageRecordDTO(
            record_id=record.record_id,
            grant_id=record.grant_id,
            tool_name=record.tool_name,
            agent_id=record.agent_id,
            timestamp=record.timestamp,
            task_id=record.task_id,
            session_id=record.session_id,
        )

    def issue_grant(self, request: IssueGrantRequestDTO) -> ApprovalGrantLeaseDTO:
        """Issue an approval grant lease under specified scope."""
        scope_enum = GrantScope(request.scope)
        lease = self._facade.issue_grant(
            tool_name=request.tool_name,
            scope=scope_enum,
            agent_id=request.agent_id,
            session_id=request.session_id,
            task_id=request.task_id,
            ttl_seconds=request.ttl_seconds,
        )
        return self._to_lease_dto(lease)

    def evaluate_risk(self, request: RiskEvaluationRequestDTO) -> RiskEvaluationResultDTO:
        """Evaluate invocation context against risk tier policies and active grants."""
        risk_enum = ActionRiskTier(request.risk_tier)
        domain_req = RiskEvaluationRequest(
            tool_name=request.tool_name,
            risk_tier=risk_enum,
            agent_id=request.agent_id,
            session_id=request.session_id,
            task_id=request.task_id,
            parameters_summary=request.parameters_summary,
        )
        res = self._facade.evaluate_and_process(domain_req)
        return RiskEvaluationResultDTO(
            decision=res.decision.value,
            reason=res.reason,
            matched_grant_id=res.matched_grant_id,
            risk_tier=res.risk_tier.value,
            requires_hitl_prompt=res.requires_hitl_prompt,
        )

    def revoke_grant(self, grant_id: str) -> RevokeGrantResponseDTO:
        """Revoke a specific approval lease."""
        success = self._facade.revoke_grant(grant_id)
        return RevokeGrantResponseDTO(success=success, grant_id=grant_id)

    def revoke_all(self, request: RevokeAllRequestDTO) -> RevokeAllResponseDTO:
        """Revoke all matching approval leases."""
        count = self._facade.revoke_all(agent_id=request.agent_id, session_id=request.session_id)
        return RevokeAllResponseDTO(revoked_count=count)

    def list_active_grants(self) -> ListActiveGrantsResponseDTO:
        """List currently valid unrevoked approval leases."""
        active = self._facade.list_active_grants()
        return ListActiveGrantsResponseDTO(grants=[self._to_lease_dto(g) for g in active])

    def get_audit_ledger(self) -> AuditLedgerResponseDTO:
        """Retrieve audit trail of grant redemptions."""
        ledger = self._facade.get_audit_ledger()
        return AuditLedgerResponseDTO(records=[self._to_record_dto(r) for r in ledger])

    def get_metrics(self) -> ScopedApprovalMetricsDTO:
        """Fetch cumulative operational metrics."""
        m = self._facade.metrics
        return ScopedApprovalMetricsDTO(
            evaluations_total=m.evaluations_total,
            silent_allows_total=m.silent_allows_total,
            asks_required_total=m.asks_required_total,
            denials_total=m.denials_total,
            grants_issued_total=m.grants_issued_total,
            grants_revoked_total=m.grants_revoked_total,
            grant_redemptions_total=m.grant_redemptions_total,
        )


_global_service: ScopedApprovalGateService | None = None


def get_scoped_approval_gate_service() -> ScopedApprovalGateService:
    """Singleton provider for ScopedApprovalGateService."""
    global _global_service
    if _global_service is None:
        _global_service = ScopedApprovalGateService()
    return _global_service
