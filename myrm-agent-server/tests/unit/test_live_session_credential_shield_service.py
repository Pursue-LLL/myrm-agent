"""
[POS] tests/unit/test_live_session_credential_shield_service.py
[INPUT] pytest, app.schemas.live_session_credential_shield, app.services.security.live_session_credential_shield_service
[OUTPUT] Unit tests for LiveSessionCredentialShieldService

Validates service-level out-of-band blind input routing, screen bounding box mask registration,
DOM password attribute redaction, and atomic handover scrubs against prompt injection.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.live_session_credential_shield import (
    AirlockChannelStatusResponse,
    BoundingBoxSchema,
    CloseAirlockRequest,
    HandoverScrubRequest,
    OpenAirlockRequest,
    RedactDOMRequest,
    RegisterMaskRegionRequest,
    RouteBlindInputRequest,
    SensitiveTargetTypeResponse,
)
from app.services.security.live_session_credential_shield_service import (
    LiveSessionCredentialShieldService,
)


def test_service_airlock_lifecycle_and_blind_routing() -> None:
    """Validate out-of-band channel management and blind input keystroke routing."""
    service = LiveSessionCredentialShieldService()
    session_id = "sess-airlock-101"

    # 1. Open airlock
    open_res = service.open_airlock(OpenAirlockRequest(session_id=session_id))
    assert open_res.status == AirlockChannelStatusResponse.OPEN

    # 2. Query status
    status_res = service.get_airlock_status(session_id)
    assert status_res.status == AirlockChannelStatusResponse.OPEN

    # 3. Route blind input
    route_res = service.route_blind_input(
        RouteBlindInputRequest(
            session_id=session_id,
            target_selector="input#master-password",
            raw_secret="StrongK3y#2026",
            target_type=SensitiveTargetTypeResponse.PASSWORD_INPUT,
        )
    )
    assert route_res.event.is_blind_routed is True
    assert route_res.event.keystroke_count == len("StrongK3y#2026")
    assert route_res.event.target_type == SensitiveTargetTypeResponse.PASSWORD_INPUT
    assert route_res.dispatch_confirmation_id.startswith("oob-disp-")

    # 4. List events
    events = service.list_session_blind_events(session_id)
    assert len(events) == 1
    assert events[0].session_id == session_id

    # 5. Close airlock
    close_res = service.close_airlock(CloseAirlockRequest(session_id=session_id))
    assert close_res.status == AirlockChannelStatusResponse.CLOSED


def test_service_mask_region_management() -> None:
    """Validate registration and retrieval of screen pixel mask bounding boxes."""
    service = LiveSessionCredentialShieldService()
    session_id = "sess-mask-202"

    region_res = service.register_mask_region(
        RegisterMaskRegionRequest(
            session_id=session_id,
            box=BoundingBoxSchema(x=50, y=100, width=300, height=40),
            target_selector="input[name='card_pin']",
            mask_color="#000000",
        )
    )
    assert region_res.region_id.startswith("mask-reg-")
    assert region_res.box.width == 300

    regions = service.list_mask_regions(session_id)
    assert len(regions) == 1
    assert regions[0].target_selector == "input[name='card_pin']"


def test_service_dom_redaction_and_handover_scrub() -> None:
    """Validate DOM credential attribute sanitization and atomic handover scrub."""
    service = LiveSessionCredentialShieldService()
    session_id = "sess-handover-303"

    # Register mask area
    service.register_mask_region(
        RegisterMaskRegionRequest(
            session_id=session_id,
            box=BoundingBoxSchema(x=20, y=30, width=150, height=35),
            target_selector="input[type='password']",
        )
    )

    # 1. Redact DOM
    dirty_dom = "<input type='password' value='cleartext_secret' /><input name='otp' value='123456' />"
    redact_res = service.redact_dom_tree(RedactDOMRequest(dom_html=dirty_dom))
    assert "cleartext_secret" not in redact_res.sanitized_dom
    assert "123456" not in redact_res.sanitized_dom
    assert "<REDACTED_CREDENTIAL>" in redact_res.sanitized_dom
    assert redact_res.redacted_nodes_count >= 2

    # 2. Handover scrub
    handover_res = service.execute_handover_scrub(
        HandoverScrubRequest(
            session_id=session_id,
            dom_html="<input type='password' value='my_bank_pwd' />",
        )
    )
    assert "my_bank_pwd" not in handover_res.sanitized_dom
    assert handover_res.report.observation_scrubbed is True
    assert handover_res.report.masked_regions_count == 1
    assert handover_res.report.redacted_dom_nodes_count == 1


def test_service_metrics() -> None:
    """Validate cumulative operational metrics."""
    service = LiveSessionCredentialShieldService()

    service.open_airlock(OpenAirlockRequest(session_id="sess-m1"))
    service.route_blind_input(
        RouteBlindInputRequest(
            session_id="sess-m1",
            target_selector="input#auth",
            raw_secret="token123",
        )
    )
    service.register_mask_region(
        RegisterMaskRegionRequest(
            session_id="sess-m1",
            box=BoundingBoxSchema(x=0, y=0, width=10, height=10),
            target_selector="input#auth",
        )
    )
    service.execute_handover_scrub(
        HandoverScrubRequest(
            session_id="sess-m1",
            dom_html="<input type='password' value='xyz' />",
        )
    )

    m = service.get_metrics()
    assert m.blind_inputs_routed_total >= 1
    assert m.screen_masks_applied_total >= 1
    assert m.handover_scrubs_completed_total >= 1
    assert m.prompt_injections_mitigated_total >= 1
