"""
[POS] app/services/security/target_scope_boundary_service.py
[INPUT] app.schemas.target_scope_boundary, myrm_agent_harness.core.security.target_scope_boundary
[OUTPUT] TargetScopeBoundaryService, get_target_scope_boundary_service

Service layer for Strict Target Scope Authorization & Egress Boundary Suite.
Coordinates Rules of Engagement (ROE) contract configuration, target verification,
and emergency kill-switch circuit breaker controls.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.target_scope_boundary import (
    ScopeVerificationResult,
    StrictTargetScopeBoundarySuite,
    TargetScopeContract,
)

from app.schemas.target_scope_boundary import (
    KillSwitchStatusResponse,
    ScopeVerificationResponse,
    SetContractRequest,
    TargetScopeContractResponse,
    TargetScopeMetricsResponse,
    VerifyTargetRequest,
)

logger = logging.getLogger(__name__)


class TargetScopeBoundaryService:
    """Service managing target scope rules of engagement contracts and egress security checks."""

    def __init__(self, suite: StrictTargetScopeBoundarySuite | None = None) -> None:
        self._suite = suite or StrictTargetScopeBoundarySuite()

    def set_contract(self, request: SetContractRequest) -> TargetScopeContractResponse:
        """Register and activate an ROE target scope authorization contract."""
        contract = TargetScopeContract(
            contract_id=request.contract_id,
            engagement_name=request.engagement_name,
            authorized_domains=tuple(request.authorized_domains),
            authorized_cidrs=tuple(request.authorized_cidrs),
            prohibited_targets=tuple(request.prohibited_targets),
            signed_by=request.signed_by,
            signature_hash=request.signature_hash,
            is_active=request.is_active,
        )
        self._suite.set_active_contract(contract)
        return self._map_contract(contract)

    def get_active_contract(self) -> TargetScopeContractResponse | None:
        """Retrieve active ROE target scope authorization contract."""
        contract = self._suite.get_active_contract()
        if contract is None:
            return None
        return self._map_contract(contract)

    def clear_contract(self) -> None:
        """Clear currently active ROE contract."""
        self._suite.set_active_contract(None)

    def verify_target(self, request: VerifyTargetRequest) -> ScopeVerificationResponse:
        """Verify destination target host against active scope contract and kill-switch."""
        res: ScopeVerificationResult = self._suite.verify_target(
            target_host=request.target_host,
            resolved_ip=request.resolved_ip,
        )
        return ScopeVerificationResponse(
            is_allowed=res.is_allowed,
            verdict=res.verdict.value,
            target_host=res.target_host,
            resolved_ip=res.resolved_ip,
            diagnostic_reason=res.diagnostic_reason,
            contract_id=res.contract_id,
        )

    def activate_kill_switch(self) -> KillSwitchStatusResponse:
        """Engage emergency kill-switch to immediately block all external scans."""
        self._suite.activate_kill_switch()
        return KillSwitchStatusResponse(
            is_kill_switch_active=True,
            message="Emergency kill-switch is ACTIVE. All outbound scanning traffic is severed.",
        )

    def reset_kill_switch(self) -> KillSwitchStatusResponse:
        """Reset emergency kill-switch to restore standard ROE policy evaluation."""
        self._suite.reset_kill_switch()
        return KillSwitchStatusResponse(
            is_kill_switch_active=False,
            message="Emergency kill-switch is DISENGAGED. Standard ROE scope rules apply.",
        )

    def get_kill_switch_status(self) -> KillSwitchStatusResponse:
        """Query current emergency kill-switch state."""
        active = self._suite.is_kill_switch_active()
        return KillSwitchStatusResponse(
            is_kill_switch_active=active,
            message="Kill-switch is ACTIVE." if active else "Kill-switch is DISENGAGED.",
        )

    def get_metrics(self) -> TargetScopeMetricsResponse:
        """Retrieve cumulative metrics for target scope verifications and egress actions."""
        m = self._suite.metrics
        return TargetScopeMetricsResponse(
            scope_checks_total=m.scope_checks_total,
            in_scope_allowed_total=m.in_scope_allowed_total,
            out_of_scope_blocked_total=m.out_of_scope_blocked_total,
            metadata_probes_blocked_total=m.metadata_probes_blocked_total,
            kill_switch_activations_total=m.kill_switch_activations_total,
        )

    @staticmethod
    def _map_contract(contract: TargetScopeContract) -> TargetScopeContractResponse:
        return TargetScopeContractResponse(
            contract_id=contract.contract_id,
            engagement_name=contract.engagement_name,
            authorized_domains=list(contract.authorized_domains),
            authorized_cidrs=list(contract.authorized_cidrs),
            prohibited_targets=list(contract.prohibited_targets),
            signed_by=contract.signed_by,
            signature_hash=contract.signature_hash,
            is_active=contract.is_active,
        )


_service_instance: TargetScopeBoundaryService | None = None


def get_target_scope_boundary_service() -> TargetScopeBoundaryService:
    """Dependency provider for TargetScopeBoundaryService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = TargetScopeBoundaryService()
    return _service_instance
