"""
[POS] tests/unit/test_autonomous_signing_airgap_service.py
[INPUT] app.schemas.autonomous_signing_airgap, app.services.security.autonomous_signing_airgap_service
[OUTPUT] Unit tests for AutonomousSigningAirgapService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.autonomous_signing_airgap import (
    ApproveStepUpRequestDTO,
    EvaluateSigningRequestDTO,
    RejectStepUpRequestDTO,
    TriggerKillSwitchRequestDTO,
    UpdateQuotaConfigRequestDTO,
)
from app.services.security.autonomous_signing_airgap_service import (
    AutonomousSigningAirgapService,
)


def test_service_evaluate_and_sign_silent() -> None:
    """Test standard headless autonomous signing for low-value whitelisted transaction."""
    service = AutonomousSigningAirgapService()
    service.update_quota_config(
        UpdateQuotaConfigRequestDTO(
            single_tx_limit=100.0,
            daily_cumulative_limit=500.0,
            trusted_recipients=["0xSafeEscrow1", "0xSafeVendor2"],
        )
    )

    verdict = service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-svc-001",
            recipient="0xSafeEscrow1",
            amount=40.0,
            currency="USDC",
            chain_or_network="base",
            call_data_summary="swap()",
        )
    )

    assert verdict.decision == "SILENT_AUTHORIZED"
    assert verdict.is_approved_to_sign is True
    assert verdict.signature_token is not None
    assert verdict.remaining_daily_allowance == 460.0


def test_service_untrusted_recipient_and_quota_rejection() -> None:
    """Test security rejections for untrusted targets and excessive amounts."""
    service = AutonomousSigningAirgapService()
    service.update_quota_config(
        UpdateQuotaConfigRequestDTO(
            single_tx_limit=100.0,
            daily_cumulative_limit=500.0,
            trusted_recipients=["0xTrustedOnly"],
        )
    )

    # 1. Untrusted recipient
    v_untrusted = service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-bad-target",
            recipient="0xMaliciousHacker",
            amount=10.0,
        )
    )
    assert v_untrusted.decision == "REJECTED_UNTRUSTED_RECIPIENT"
    assert v_untrusted.is_approved_to_sign is False

    # 2. Extreme quota breach (>3x single limit)
    v_huge = service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-huge",
            recipient="0xTrustedOnly",
            amount=400.0,
        )
    )
    assert v_huge.decision == "REJECTED_QUOTA_EXCEEDED"
    assert v_huge.is_approved_to_sign is False


def test_service_step_up_escalation_approval_and_rejection() -> None:
    """Test human-in-the-loop step-up workflow: hold, list, approve, and reject."""
    service = AutonomousSigningAirgapService()
    service.update_quota_config(
        UpdateQuotaConfigRequestDTO(
            single_tx_limit=100.0,
            daily_cumulative_limit=500.0,
            trusted_recipients=["0xPartnerContract"],
        )
    )

    # Trigger Step-Up HITL
    v_held = service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-escalate-1",
            recipient="0xPartnerContract",
            amount=180.0,
        )
    )
    assert v_held.decision == "REQUIRE_HITL_STEP_UP"
    assert v_held.is_approved_to_sign is False

    pending = service.list_pending_step_up()
    assert len(pending) == 1
    assert pending[0].tx_id == "tx-escalate-1"

    # Human approves
    v_approved = service.approve_step_up(
        ApproveStepUpRequestDTO(
            tx_id="tx-escalate-1",
            approver_note="Risk verified by finance lead",
        )
    )
    assert v_approved is not None
    assert v_approved.decision == "SILENT_AUTHORIZED"
    assert v_approved.is_approved_to_sign is True
    assert v_approved.signature_token is not None

    # Test rejection workflow for second item
    service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-escalate-2",
            recipient="0xPartnerContract",
            amount=120.0,
        )
    )
    assert len(service.list_pending_step_up()) == 1

    rejected = service.reject_step_up(
        RejectStepUpRequestDTO(tx_id="tx-escalate-2", reason="Disapproved")
    )
    assert rejected is True
    assert len(service.list_pending_step_up()) == 0


def test_service_kill_switch_lifecycle() -> None:
    """Test global emergency kill-switch freeze, blocking all operations until released."""
    service = AutonomousSigningAirgapService()

    # Trigger freeze
    freeze_resp = service.trigger_kill_switch(
        TriggerKillSwitchRequestDTO(reason="Anomalous prompt attack detected")
    )
    assert freeze_resp.is_kill_switch_active is True
    assert freeze_resp.kill_switch_reason == "Anomalous prompt attack detected"

    # Transaction rejected under freeze
    v_frozen = service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-under-freeze",
            recipient="0xSafeVendor",
            amount=5.0,
        )
    )
    assert v_frozen.decision == "FROZEN_BY_KILL_SWITCH"
    assert v_frozen.is_approved_to_sign is False

    # Release freeze
    rel_resp = service.release_kill_switch()
    assert rel_resp.is_kill_switch_active is False

    status = service.get_kill_switch_status()
    assert status.is_kill_switch_active is False


def test_service_quota_and_metrics() -> None:
    """Test quota retrieval and metric tracking."""
    service = AutonomousSigningAirgapService()

    # Initial evaluation
    service.evaluate_and_sign(
        EvaluateSigningRequestDTO(
            tx_id="tx-m1",
            recipient="0xTarget",
            amount=10.0,
        )
    )

    metrics = service.get_metrics()
    assert metrics.evaluations_total >= 1
    assert metrics.silent_signed_total >= 1

    quota = service.get_quota_config()
    assert quota.single_tx_limit > 0
    assert quota.current_daily_spent >= 10.0
