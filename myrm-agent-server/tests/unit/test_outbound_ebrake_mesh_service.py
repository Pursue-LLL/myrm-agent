"""
[POS] tests/unit/test_outbound_ebrake_mesh_service.py
[INPUT] app.schemas.outbound_ebrake_mesh, app.services.security.outbound_ebrake_mesh_service
[OUTPUT] Unit tests for OutboundEBrakeMeshService

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time

from app.schemas.outbound_ebrake_mesh import (
    CalendarTimeSlotDTO,
    CancelOutboundActionRequestDTO,
    EnqueueOutboundActionRequestDTO,
    InspectOutboundActionRequestDTO,
    NegotiateCalendarRequestDTO,
    TriggerEBrakeRequestDTO,
)
from app.services.security.outbound_ebrake_mesh_service import (
    OutboundEBrakeMeshService,
)


def test_service_inspect_outbound_action() -> None:
    """Test ghost pre-flight inspection for internal, external, and exfiltration attempts."""
    service = OutboundEBrakeMeshService()

    # 1. Internal clean inspection
    r1 = service.inspect_outbound_action(
        InspectOutboundActionRequestDTO(
            action_type="EMAIL_DISPATCH",
            destination_target="reports@myrm.internal",
            payload_text="Quarterly review metrics report",
        )
    )
    assert r1.is_safe_to_queue is True
    assert r1.risk_tier == "INTERNAL_SAFE"
    assert len(r1.tainted_tokens_detected) == 0

    # 2. Trusted external webhook
    r2 = service.inspect_outbound_action(
        InspectOutboundActionRequestDTO(
            action_type="WEBHOOK_CALL",
            destination_target="https://api.github.com/webhook",
            payload_text="Sync repo workflow trigger",
        )
    )
    assert r2.is_safe_to_queue is True
    assert r2.risk_tier == "EXTERNAL_TRUSTED"

    # 3. Secret leak attempt to external recipient
    r3 = service.inspect_outbound_action(
        InspectOutboundActionRequestDTO(
            action_type="EMAIL_DISPATCH",
            destination_target="recipient@external.com",
            payload_text="Config contains AWS credential: AKIA1234567890ABCDEF",
        )
    )
    assert r3.is_safe_to_queue is False
    assert r3.risk_tier == "PROHIBITED_LEAK"
    assert "AWS_KEY" in r3.tainted_tokens_detected


def test_service_queue_cancel_and_flush_lifecycle() -> None:
    """Test enqueuing into grace buffer, manual cancellation, and instant flush."""
    service = OutboundEBrakeMeshService()

    # 1. Enqueue action
    item = service.enqueue_action(
        EnqueueOutboundActionRequestDTO(
            task_id="task-email-44",
            action_type="EMAIL_DISPATCH",
            destination_target="bob@corp.internal",
            payload_text="Team sync scheduled for Friday",
            grace_period_seconds=10.0,
        )
    )
    assert item.action_id.startswith("act-")
    assert item.status == "QUEUED_IN_GRACE_PERIOD"

    # 2. Get action
    fetched = service.get_action(item.action_id)
    assert fetched is not None
    assert fetched.destination_target == "bob@corp.internal"

    # 3. Cancel action
    cancelled = service.cancel_action(
        item.action_id,
        CancelOutboundActionRequestDTO(reason="Operator cancelled via WebUI"),
    )
    assert cancelled is True

    fetched_cancelled = service.get_action(item.action_id)
    assert fetched_cancelled is not None
    assert fetched_cancelled.status == "CANCELLED_BY_USER"
    assert fetched_cancelled.cancellation_reason == "Operator cancelled via WebUI"

    # 4. Enqueue second item and flush
    item2 = service.enqueue_action(
        EnqueueOutboundActionRequestDTO(
            task_id="task-flush-45",
            action_type="IM_BROADCAST",
            destination_target="#general",
            payload_text="Important release announcement",
            grace_period_seconds=15.0,
        )
    )
    flushed = service.flush_action(item2.action_id)
    assert flushed is True

    fetched_flushed = service.get_action(item2.action_id)
    assert fetched_flushed is not None
    assert fetched_flushed.status == "DISPATCHED_AFTER_GRACE"


def test_service_poll_dispatch_timeout() -> None:
    """Test timeout dispatch after grace period expires."""
    service = OutboundEBrakeMeshService()

    item = service.enqueue_action(
        EnqueueOutboundActionRequestDTO(
            task_id="task-timeout-1",
            action_type="WEBHOOK_CALL",
            destination_target="https://slack.com/api/chat",
            payload_text="Server ping",
            grace_period_seconds=5.0,
        )
    )
    assert item.status == "QUEUED_IN_GRACE_PERIOD"

    # Sleep past minimum grace threshold
    time.sleep(5.1)

    dispatched = service.poll_and_dispatch()
    assert any(x.action_id == item.action_id for x in dispatched)


def test_service_emergency_e_brake_hard_stop() -> None:
    """Test physical e-brake aborting all queued items instantly."""
    service = OutboundEBrakeMeshService()

    # Enqueue multiple actions
    item1 = service.enqueue_action(
        EnqueueOutboundActionRequestDTO(
            task_id="task-ebrake-1",
            action_type="EMAIL_DISPATCH",
            destination_target="user@domain.com",
            payload_text="Outbound bulk email 1",
            grace_period_seconds=30.0,
        )
    )
    item2 = service.enqueue_action(
        EnqueueOutboundActionRequestDTO(
            task_id="task-ebrake-2",
            action_type="SOCIAL_POST",
            destination_target="x.com/post",
            payload_text="Outbound announcement 2",
            grace_period_seconds=30.0,
        )
    )

    queued = service.list_queued_actions()
    assert len(queued) >= 2

    # Trigger E-Brake
    aborted_count = service.trigger_e_brake(
        TriggerEBrakeRequestDTO(reason="Hardware emergency red button hit")
    )
    assert aborted_count >= 2

    status = service.get_e_brake_status()
    assert status.is_e_brake_active is True
    assert status.trigger_reason == "Hardware emergency red button hit"

    # Verify aborted status
    f1 = service.get_action(item1.action_id)
    assert f1 is not None
    assert f1.status == "ABORTED_BY_E_BRAKE"

    f2 = service.get_action(item2.action_id)
    assert f2 is not None
    assert f2.status == "ABORTED_BY_E_BRAKE"

    # Reset
    reset_ok = service.reset_e_brake()
    assert reset_ok is True
    assert service.get_e_brake_status().is_e_brake_active is False


def test_service_privacy_preserving_calendar_negotiation() -> None:
    """Test zero-knowledge calendar negotiation through service layer."""
    service = OutboundEBrakeMeshService()

    slots_a = [
        CalendarTimeSlotDTO(slot_index=0, start_time_iso="2026-10-09T14:00:00Z", is_free=True, preference_score=0.9),
        CalendarTimeSlotDTO(slot_index=1, start_time_iso="2026-10-09T14:30:00Z", is_free=False, preference_score=0.0),
    ]
    slots_b = [
        CalendarTimeSlotDTO(slot_index=0, start_time_iso="2026-10-09T14:00:00Z", is_free=True, preference_score=0.8),
        CalendarTimeSlotDTO(slot_index=1, start_time_iso="2026-10-09T14:30:00Z", is_free=True, preference_score=0.5),
    ]

    res = service.negotiate_calendar(
        NegotiateCalendarRequestDTO(
            party_a_id="cos-lead-a",
            party_b_id="cos-lead-b",
            party_a_slots=slots_a,
            party_b_slots=slots_b,
        )
    )
    assert res.privacy_preserved is True
    assert len(res.matched_slots) == 1
    assert res.optimal_slot is not None
    assert res.optimal_slot.slot_index == 0
    assert round(res.optimal_slot.preference_score, 2) == 1.7

    metrics = service.get_metrics()
    assert metrics.calendar_negotiations_total >= 1
