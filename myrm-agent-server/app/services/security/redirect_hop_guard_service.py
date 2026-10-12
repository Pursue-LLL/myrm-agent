"""Business service for Redirect Private Address Hop Revalidation Suite.

[INPUT]
- app.schemas.redirect_hop_guard::(HopEvaluationRequest, HopEvaluationResponse, HopPolicyConfigRequest, HopPolicyConfigResponse, HopViolationRecordResponse, HopViolationsListResponse, HopSimulationRequest)
- myrm_agent_harness.core.security.redirect_hop_guard::(RedirectHopGuardFacade, RedirectHopGuardConfig, HopViolationAuditRecord, HopDisposition)
- stdlib datetime, threading

[OUTPUT]
- RedirectHopGuardService: singleton service managing hop revalidation, policies, and audits

[POS]
Service layer bridging REST API endpoints to harness RedirectHopGuardFacade.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from myrm_agent_harness.core.security.redirect_hop_guard import (
    HopDisposition,
    HopViolationAuditRecord,
    RedirectHopGuardConfig,
    RedirectHopGuardFacade,
)

from app.schemas.redirect_hop_guard import (
    HopEvaluationRequest,
    HopEvaluationResponse,
    HopPolicyConfigRequest,
    HopPolicyConfigResponse,
    HopSimulationRequest,
    HopViolationRecordResponse,
    HopViolationsListResponse,
)


class RedirectHopGuardService:
    """Service orchestrating hop-by-hop redirect verification and violation auditing."""

    _instance: RedirectHopGuardService | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self) -> None:
        self._facade: RedirectHopGuardFacade = RedirectHopGuardFacade()

    @classmethod
    def get_instance(cls) -> RedirectHopGuardService:
        """Thread-safe singleton accessor."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance for testing environments."""
        with cls._lock:
            cls._instance = None

    def evaluate_hop(self, request: HopEvaluationRequest) -> HopEvaluationResponse:
        """Evaluate a target URL against active hop protection policies."""
        result = self._facade.evaluate_hop(
            target_url=request.target_url,
            resource_type=request.resource_type,
        )
        return HopEvaluationResponse(
            disposition=result.disposition.value,
            is_private=result.is_private,
            matched_rule=result.matched_rule,
            target_url=result.target_url,
            resource_type=result.resource_type,
            reason=result.reason,
        )

    def get_policy(self) -> HopPolicyConfigResponse:
        """Retrieve current policy configuration."""
        cfg = self._facade.config
        return HopPolicyConfigResponse(
            allow_private_networks=cfg.allow_private_networks,
            reset_to_about_blank=cfg.reset_to_about_blank,
            audit_history_max_size=cfg.audit_history_max_size,
            custom_blocked_hostnames=list(cfg.custom_blocked_hostnames),
        )

    def update_policy(self, request: HopPolicyConfigRequest) -> HopPolicyConfigResponse:
        """Update policy configuration on the facade."""
        new_config = RedirectHopGuardConfig(
            allow_private_networks=request.allow_private_networks,
            reset_to_about_blank=request.reset_to_about_blank,
            audit_history_max_size=request.audit_history_max_size,
            custom_blocked_hostnames=tuple(request.custom_blocked_hostnames),
        )
        self._facade.update_config(new_config)
        return self.get_policy()

    def simulate_violation(self, request: HopSimulationRequest) -> HopViolationRecordResponse:
        """Simulate a hop evaluation and record a violation event if blocked."""
        eval_result = self._facade.evaluate_hop(
            target_url=request.hop_url,
            resource_type=request.resource_type,
        )

        timestamp = datetime.now(UTC).isoformat()
        disposition = eval_result.disposition
        if disposition == HopDisposition.ALLOW:
            # Force simulated document reset disposition if testing simulation
            disposition = HopDisposition.ABORT_AND_RESET_DOCUMENT

        record = HopViolationAuditRecord(
            timestamp_iso=timestamp,
            initial_url=request.initial_url,
            hop_url=request.hop_url,
            resource_type=request.resource_type,
            disposition=disposition,
            matched_rule=eval_result.matched_rule if eval_result.is_private else "SIMULATED_HOP_RULE",
            reason=eval_result.reason if eval_result.is_private else "Simulated violation interception",
        )

        # Inject into facade violation history
        with self._facade._lock:
            self._facade._violations.append(record)

        return HopViolationRecordResponse(
            timestamp_iso=record.timestamp_iso,
            initial_url=record.initial_url,
            hop_url=record.hop_url,
            resource_type=record.resource_type,
            disposition=record.disposition.value,
            matched_rule=record.matched_rule,
            reason=record.reason,
        )

    def get_violations(self) -> HopViolationsListResponse:
        """Return all recorded hop violations."""
        records = self._facade.get_violations()
        items = [
            HopViolationRecordResponse(
                timestamp_iso=r.timestamp_iso,
                initial_url=r.initial_url,
                hop_url=r.hop_url,
                resource_type=r.resource_type,
                disposition=r.disposition.value,
                matched_rule=r.matched_rule,
                reason=r.reason,
            )
            for r in records
        ]
        return HopViolationsListResponse(total=len(items), violations=items)

    def clear_violations(self) -> None:
        """Clear all recorded violation logs."""
        self._facade.clear_violations()
