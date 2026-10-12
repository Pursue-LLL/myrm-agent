"""
[POS] tests/unit/test_data_sovereignty_watchdog_service.py
[INPUT] pytest, time, app.schemas.data_sovereignty_watchdog, app.services.security.data_sovereignty_watchdog_service
[OUTPUT] Unit tests for DataSovereigntyWatchdogService

Validates service-level private volume data sovereignty certification, anti-annoyance card gating,
and high-stakes action human consent ticketing.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from app.schemas.data_sovereignty_watchdog import (
    ConsentDecisionRequest,
    CreateConsentTicketRequest,
    EvaluateSuggestionRequest,
    HighStakesActionTypeResponse,
    IssueSovereigntySealRequest,
    ProactivityValueLevelResponse,
    SovereigntySealLevelResponse,
    VerifySovereigntySealRequest,
)
from app.services.security.data_sovereignty_watchdog_service import (
    DataSovereigntyWatchdogService,
)


def test_service_sovereignty_seal() -> None:
    """Validate data sovereignty sealing and verification."""
    service = DataSovereigntyWatchdogService()

    # 1. Issue seal
    seal_res = service.issue_sovereignty_seal(
        IssueSovereigntySealRequest(
            storage_target="sqlite:///data/private/finances.db",
            volume_mount_path="/mnt/user_volume_private",
            seal_level=SovereigntySealLevelResponse.PRIVATE_SANDBOX_VOLUME,
        )
    )
    assert seal_res.seal_id.startswith("seal-")
    assert seal_res.central_cloud_zero_retention is True
    assert len(seal_res.checksum) == 64

    # 2. Verify seal
    verify_res = service.verify_sovereignty_seal(
        VerifySovereigntySealRequest(seal_id=seal_res.seal_id)
    )
    assert verify_res.is_valid is True

    # 3. Latest seal
    latest = service.get_latest_seal()
    assert latest is not None
    assert latest.seal_id == seal_res.seal_id


def test_service_watchdog_evaluation_and_cards() -> None:
    """Validate watchdog noise suppression and card retrieval."""
    service = DataSovereigntyWatchdogService()
    now = time.time()

    # 1. Suppressed suggestion ($3.00, no deadline)
    card_noise = service.evaluate_proactive_suggestion(
        EvaluateSuggestionRequest(
            title="Slight disk saving",
            service_name="DropBox",
            potential_savings_cents=300,
            deadline_epoch=None,
            message="Clean trash to save 3 dollars.",
        )
    )
    assert card_noise.is_suppressed is True
    assert card_noise.value_level == ProactivityValueLevelResponse.MODERATE_SUGGESTION

    # 2. Emitted suggestion ($40.00)
    card_high = service.evaluate_proactive_suggestion(
        EvaluateSuggestionRequest(
            title="Unused SaaS seat",
            service_name="SlackWorkspace",
            potential_savings_cents=4000,
            deadline_epoch=None,
            message="Deactivate unused member seat.",
        )
    )
    assert card_high.is_suppressed is False
    assert card_high.value_level == ProactivityValueLevelResponse.HIGH_VALUE_ALERT

    # 3. Critical deadline (12 hours)
    card_deadline = service.evaluate_proactive_suggestion(
        EvaluateSuggestionRequest(
            title="Subscription renewal imminent",
            service_name="DomainRegistrar",
            potential_savings_cents=1500,
            deadline_epoch=now + 43200.0,
            message="Renew or cancel within 12 hours.",
        )
    )
    assert card_deadline.is_suppressed is False
    assert card_deadline.value_level == ProactivityValueLevelResponse.CRITICAL_DEADLINE

    # 4. Check active vs all
    active = service.list_active_notification_cards()
    assert len(active) == 2
    assert all(not c.is_suppressed for c in active)

    all_cards = service.list_all_notification_cards()
    assert len(all_cards) == 3


def test_service_consent_lifecycle() -> None:
    """Validate high-stakes consent ticket lifecycle."""
    service = DataSovereigntyWatchdogService()

    # 1. Create ticket
    ticket_res = service.create_high_stakes_consent(
        CreateConsentTicketRequest(
            action_type=HighStakesActionTypeResponse.SUBSCRIPTION_CANCEL,
            service_name="Netflix Premium",
            financial_impact_cents=2299,
            payload_summary="Cancel $22.99 monthly plan",
        )
    )
    assert ticket_res.ticket_id.startswith("ticket-")
    assert ticket_res.is_approved is False
    assert ticket_res.is_denied is False

    pending = service.list_pending_consents()
    assert len(pending) == 1
    assert pending[0].ticket_id == ticket_res.ticket_id

    # 2. Approve ticket
    approved = service.approve_consent(ConsentDecisionRequest(ticket_id=ticket_res.ticket_id))
    assert approved.is_approved is True
    assert len(service.list_pending_consents()) == 0

    # 3. Create and deny another ticket
    t2 = service.create_high_stakes_consent(
        CreateConsentTicketRequest(
            action_type=HighStakesActionTypeResponse.BALANCE_TRANSFER,
            service_name="Wise Account",
            financial_impact_cents=50000,
            payload_summary="Transfer $500 balance",
        )
    )
    denied = service.deny_consent(ConsentDecisionRequest(ticket_id=t2.ticket_id))
    assert denied.is_denied is True


def test_service_metrics() -> None:
    """Validate cumulative operational metrics."""
    service = DataSovereigntyWatchdogService()

    service.issue_sovereignty_seal(
        IssueSovereigntySealRequest(
            storage_target="local",
            volume_mount_path="/mnt/vol",
        )
    )
    service.evaluate_proactive_suggestion(
        EvaluateSuggestionRequest(
            title="t",
            service_name="s",
            potential_savings_cents=50,
        )
    )
    t = service.create_high_stakes_consent(
        CreateConsentTicketRequest(
            action_type=HighStakesActionTypeResponse.PAYMENT_METHOD_UPDATE,
            service_name="Stripe",
            financial_impact_cents=0,
            payload_summary="Update card",
        )
    )
    service.approve_consent(ConsentDecisionRequest(ticket_id=t.ticket_id))

    metrics = service.get_metrics()
    assert metrics.sovereignty_seals_issued_total >= 1
    assert metrics.proactive_scans_total >= 1
    assert metrics.noise_suppressed_total >= 1
    assert metrics.high_stakes_actions_blocked_total >= 1
    assert metrics.high_stakes_consents_approved_total >= 1
