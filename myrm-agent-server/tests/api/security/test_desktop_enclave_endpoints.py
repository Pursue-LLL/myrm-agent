"""Integration tests for Desktop Safe Enclave API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.desktop_enclave_router import router as desktop_enclave_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting desktop_enclave_router."""
    test_app = FastAPI(title="Desktop Enclave Test App")
    test_app.include_router(desktop_enclave_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_evaluate_desktop_action_endpoint(client: TestClient) -> None:
    # 1. Safe action
    safe_payload = {
        "action": {
            "action_id": "act_api_01",
            "action_type": "mouse_click",
            "semantic_intent": "切换至日志标签页",
            "target_element_text": "Logs Tab",
        }
    }
    resp = client.post("/api/v1/security/desktop-enclave/evaluate", json=safe_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["allowed"] is True
    assert data["challenge"] is None

    # 2. Critical action
    crit_payload = {
        "action": {
            "action_id": "act_api_02",
            "action_type": "mouse_click",
            "semantic_intent": "点击确认付款",
            "target_element_text": "立即支付 199 元",
        }
    }
    resp_crit = client.post("/api/v1/security/desktop-enclave/evaluate", json=crit_payload)
    assert resp_crit.status_code == 200
    data_crit = resp_crit.json()
    assert data_crit["allowed"] is False
    assert data_crit["challenge"] is not None
    assert data_crit["challenge"]["status"] == "pending"


def test_decide_challenge_and_list_pending(client: TestClient) -> None:
    # Intercept an action first
    crit_payload = {
        "action": {
            "action_id": "act_api_03",
            "action_type": "system_command",
            "semantic_intent": "格式化并抹掉磁盘数据",
            "payload_text": "format disk",
        }
    }
    resp_crit = client.post("/api/v1/security/desktop-enclave/evaluate", json=crit_payload)
    chal_id = resp_crit.json()["challenge"]["challenge_id"]

    # List pending
    list_resp = client.get("/api/v1/security/desktop-enclave/challenges/pending")
    assert list_resp.status_code == 200
    pending_ids = [ch["challenge_id"] for ch in list_resp.json()]
    assert chal_id in pending_ids

    # Approve challenge
    decide_payload = {
        "challenge_id": chal_id,
        "approved": True,
        "reason": "Authorized by system administrator",
    }
    decide_resp = client.post("/api/v1/security/desktop-enclave/decide", json=decide_payload)
    assert decide_resp.status_code == 200
    decide_data = decide_resp.json()
    assert decide_data["status"] == "approved"
    assert decide_data["action"]["action_id"] == "act_api_03"


def test_panic_controls_and_live_hud_endpoints(client: TestClient) -> None:
    # Initial status
    status_resp = client.get("/api/v1/security/desktop-enclave/panic/status")
    assert status_resp.status_code == 200
    assert "is_panicked" in status_resp.json()

    # Trigger panic
    trigger_resp = client.post(
        "/api/v1/security/desktop-enclave/panic",
        json={"reason": "Red button pressed in test suite"},
    )
    assert trigger_resp.status_code == 200
    assert trigger_resp.json()["is_panicked"] is True

    # Evaluate while panicked is blocked
    resp_blocked = client.post(
        "/api/v1/security/desktop-enclave/evaluate",
        json={
            "action": {
                "action_id": "act_blocked",
                "action_type": "mouse_click",
                "semantic_intent": "测试点击",
            }
        },
    )
    assert resp_blocked.status_code == 200
    assert resp_blocked.json()["allowed"] is False
    assert "Emergency panic active" in resp_blocked.json()["reason"]

    # Reset panic
    reset_resp = client.post("/api/v1/security/desktop-enclave/panic/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["is_panicked"] is False

    # Live HUD
    hud_resp = client.get("/api/v1/security/desktop-enclave/live-hud?limit=10")
    assert hud_resp.status_code == 200
    hud_data = hud_resp.json()
    assert "feed" in hud_data
    assert "count" in hud_data
