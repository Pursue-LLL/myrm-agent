"""
[POS] app/services/security/autonomous_signing_airgap_service.py
[INPUT] app.schemas.autonomous_signing_airgap, myrm_agent_harness.core.security.autonomous_signing_airgap
[OUTPUT] AutonomousSigningAirgapService, get_autonomous_signing_airgap_service
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.autonomous_signing_airgap import (
    AutonomousSigningAirgapFacade,
    SigningQuotaConfig,
    TransactionPayload,
)

from app.schemas.autonomous_signing_airgap import (
    ApproveStepUpRequestDTO,
    EvaluateSigningRequestDTO,
    KillSwitchStatusResponseDTO,
    QuotaConfigResponseDTO,
    RejectStepUpRequestDTO,
    SigningVerdictResponseDTO,
    TriggerKillSwitchRequestDTO,
    UpdateQuotaConfigRequestDTO,
    WalletAirgapMetricsResponseDTO,
)

logger = logging.getLogger(__name__)


class AutonomousSigningAirgapService:
    """Service mediating transaction inspection, quota guarding, and airgapped signing."""

    def __init__(
        self, facade: AutonomousSigningAirgapFacade | None = None
    ) -> None:
        self._facade = facade or AutonomousSigningAirgapFacade()

    def evaluate_and_sign(
        self, request: EvaluateSigningRequestDTO
    ) -> SigningVerdictResponseDTO:
        """Inspect and conditionally sign proposed transaction."""
        payload = TransactionPayload(
            tx_id=request.tx_id,
            recipient=request.recipient,
            amount=request.amount,
            currency=request.currency,
            chain_or_network=request.chain_or_network,
            call_data_summary=request.call_data_summary,
            metadata=request.metadata,
        )
        verdict = self._facade.evaluate_and_sign(payload)
        return SigningVerdictResponseDTO(
            decision=verdict.decision.value,
            is_approved_to_sign=verdict.is_approved_to_sign,
            signature_token=verdict.signature_token,
            diagnostic_reason=verdict.diagnostic_reason,
            tx_id=verdict.tx_id,
            remaining_daily_allowance=verdict.remaining_daily_allowance,
        )

    def approve_step_up(
        self, request: ApproveStepUpRequestDTO
    ) -> SigningVerdictResponseDTO | None:
        """Process explicit operator approval for a pending stepped-up transaction."""
        verdict = self._facade.approve_stepped_up_tx(
            tx_id=request.tx_id, approver_note=request.approver_note
        )
        if verdict is None:
            return None
        return SigningVerdictResponseDTO(
            decision=verdict.decision.value,
            is_approved_to_sign=verdict.is_approved_to_sign,
            signature_token=verdict.signature_token,
            diagnostic_reason=verdict.diagnostic_reason,
            tx_id=verdict.tx_id,
            remaining_daily_allowance=verdict.remaining_daily_allowance,
        )

    def reject_step_up(self, request: RejectStepUpRequestDTO) -> bool:
        """Reject and drop a pending stepped-up transaction."""
        logger.info("Step-up transaction %s rejected: %s", request.tx_id, request.reason)
        return self._facade.reject_stepped_up_tx(request.tx_id)

    def list_pending_step_up(self) -> list[EvaluateSigningRequestDTO]:
        """List transactions awaiting human confirmation."""
        pending = self._facade.list_pending_hitl_txs()
        return [
            EvaluateSigningRequestDTO(
                tx_id=p.tx_id,
                recipient=p.recipient,
                amount=p.amount,
                currency=p.currency,
                chain_or_network=p.chain_or_network,
                call_data_summary=p.call_data_summary,
                metadata=dict(p.metadata),
            )
            for p in pending
        ]

    def trigger_kill_switch(
        self, request: TriggerKillSwitchRequestDTO
    ) -> KillSwitchStatusResponseDTO:
        """Activate emergency wallet kill-switch freeze."""
        self._facade.trigger_kill_switch(reason=request.reason)
        return self.get_kill_switch_status()

    def release_kill_switch(self) -> KillSwitchStatusResponseDTO:
        """Deactivate emergency wallet kill-switch freeze."""
        self._facade.release_kill_switch()
        return self.get_kill_switch_status()

    def get_kill_switch_status(self) -> KillSwitchStatusResponseDTO:
        """Fetch current kill-switch state."""
        return KillSwitchStatusResponseDTO(
            is_kill_switch_active=self._facade.is_kill_switch_active,
            kill_switch_reason=self._facade.kill_switch_reason,
        )

    def get_quota_config(self) -> QuotaConfigResponseDTO:
        """Get active signing quota thresholds and usage."""
        cfg = self._facade.get_quota_config()
        remaining = max(0.0, cfg.daily_cumulative_limit - self._facade.current_daily_spent)
        return QuotaConfigResponseDTO(
            single_tx_limit=cfg.single_tx_limit,
            daily_cumulative_limit=cfg.daily_cumulative_limit,
            trusted_recipients=list(cfg.trusted_recipients),
            current_daily_spent=self._facade.current_daily_spent,
            remaining_daily_allowance=remaining,
        )

    def update_quota_config(
        self, request: UpdateQuotaConfigRequestDTO
    ) -> QuotaConfigResponseDTO:
        """Update quota rules and recipient whitelist."""
        cfg = SigningQuotaConfig(
            single_tx_limit=request.single_tx_limit,
            daily_cumulative_limit=request.daily_cumulative_limit,
            trusted_recipients=tuple(request.trusted_recipients),
        )
        self._facade.update_quota_config(cfg)
        return self.get_quota_config()

    def get_metrics(self) -> WalletAirgapMetricsResponseDTO:
        """Retrieve operational metric counters."""
        m = self._facade.metrics
        return WalletAirgapMetricsResponseDTO(
            evaluations_total=m.evaluations_total,
            silent_signed_total=m.silent_signed_total,
            hitl_stepped_up_total=m.hitl_stepped_up_total,
            rejected_quota_total=m.rejected_quota_total,
            rejected_untrusted_total=m.rejected_untrusted_total,
            kill_switch_blocked_total=m.kill_switch_blocked_total,
        )


_global_service: AutonomousSigningAirgapService | None = None


def get_autonomous_signing_airgap_service() -> AutonomousSigningAirgapService:
    """Singleton provider for AutonomousSigningAirgapService."""
    global _global_service
    if _global_service is None:
        _global_service = AutonomousSigningAirgapService()
    return _global_service
