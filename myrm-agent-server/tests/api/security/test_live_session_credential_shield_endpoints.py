"""
[POS] tests/api/security/test_live_session_credential_shield_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.live_session_credential_shield_router, app.services.security.live_session_credential_shield_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for Live Session Out-of-Band Credential Input Shield Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.live_session_credential_shield_router import (
    router as live_shield_router,
)
from app.services.security.live_session_credential_shield_service import (
    LiveSessionCredentialShieldService,
    get_live_session_credential_shield_service,
)


@pytest.fixture
def client() -> TestClient:
    service = LiveSessionCredentialShieldService()
    app = FastAPI()
    app.include_router(live_shield_router)
    app.dependency_overrides[get_live_session_credential_shield_service] = lambda: service
    return TestClient(app)


def test_airlock_channel_and_blind_input_endpoints(client: TestClient) -> None:
    """Validate POST /airlock/open, route-blind-input, events, and close endpoints."""
    session_id = "sess-api-01"

    # 1. Open airlock
    open_res = client.post(
        "/live-session-credential-shield/airlock/open",
        json={"session_id": session_id},
    )
    assert open_res.status_code == 200
    assert open_res.json()["status"] == "OPEN"

    # 2. Get status
    status_res = client.get(f"/live-session-credential-shield/airlock/{session_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "OPEN"

    # 3. Route blind input
    route_res = client.post(
        "/live-session-credential-shield/airlock/route-blind-input",
        json={
            "session_id": session_id,
            "target_selector": "input#pin",
            "raw_secret": "123456",
            "target_type": "OTP_INPUT",
        },
    )
    assert route_res.status_code == 200
    rdata = route_res.json()
    assert rdata["event"]["is_blind_routed"] is True
    assert rdata["event"]["keystroke_count"] == 6
    assert rdata["dispatch_confirmation_id"].startswith("oob-disp-")

    # 4. List blind events
    events_res = client.get(f"/live-session-credential-shield/airlock/{session_id}/events")
    assert events_res.status_code == 200
    assert len(events_res.json()) == 1

    # 5. Close airlock
    close_res = client.post(
        "/live-session-credential-shield/airlock/close",
        json={"session_id": session_id},
    )
    assert close_res.status_code == 200
    assert close_res.json()["status"] == "CLOSED"


def test_masking_and_redaction_endpoints(client: TestClient) -> None:
    """Validate screen mask registration, DOM redaction, and handover scrub endpoints."""
    session_id = "sess-api-02"

    # 1. Register mask region
    reg_res = client.post(
        "/live-session-credential-shield/masking/regions",
        json={
            "session_id": session_id,
            "box": {"x": 100, "y": 200, "width": 250, "height": 30},
            "target_selector": "input[type='password']",
            "mask_color": "#000000",
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["region_id"].startswith("mask-reg-")

    # 2. List mask regions
    list_res = client.get(f"/live-session-credential-shield/masking/regions/{session_id}")
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 3. Redact DOM
    dom_res = client.post(
        "/live-session-credential-shield/redaction/dom",
        json={
            "dom_html": "<div><input type='password' value='supersecret' /></div>",
        },
    )
    assert dom_res.status_code == 200
    ddata = dom_res.json()
    assert "supersecret" not in ddata["sanitized_dom"]
    assert "<REDACTED_CREDENTIAL>" in ddata["sanitized_dom"]
    assert ddata["redacted_nodes_count"] >= 1

    # 4. Handover scrub
    handover_res = client.post(
        "/live-session-credential-shield/handover/scrub",
        json={
            "session_id": session_id,
            "dom_html": "<input type='password' value='mypass' />",
        },
    )
    assert handover_res.status_code == 200
    hdata = handover_res.json()
    assert "mypass" not in hdata["sanitized_dom"]
    assert hdata["report"]["observation_scrubbed"] is True
    assert hdata["report"]["masked_regions_count"] == 1

    # 5. Metrics
    metrics_res = client.get("/live-session-credential-shield/metrics")
    assert metrics_res.status_code == 200
    mdata = metrics_res.json()
    assert mdata["screen_masks_applied_total"] == 1
    assert mdata["handover_scrubs_completed_total"] == 1
