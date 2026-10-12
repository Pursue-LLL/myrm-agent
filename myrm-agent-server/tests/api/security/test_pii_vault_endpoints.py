"""Integration tests for PII Vault and Pseudonymization API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.pii_vault_router import router as pii_vault_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting pii_vault_router."""
    test_app = FastAPI(title="PII Vault Test App")
    test_app.include_router(pii_vault_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_detect_pii_endpoint(client: TestClient) -> None:
    payload = {
        "text": "学生：孙七，学号：202300555，联系电话：13600002222",
    }
    resp = client.post("/api/v1/security/pii-vault/detect", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 3
    entity_types = [m["entity_type"] for m in data["matches"]]
    assert "chinese_name" in entity_types
    assert "student_id" in entity_types
    assert "phone_number" in entity_types


def test_sanitize_and_desanitize_lifecycle_endpoints(client: TestClient) -> None:
    session_id = "sess_api_pii_01"

    # 1. Sanitize outbound payload
    san_payload = {
        "text": "教师：钱八，手机：13511119999，身份证：110101198506051234",
        "session_id": session_id,
    }
    san_resp = client.post("/api/v1/security/pii-vault/sanitize", json=san_payload)
    assert san_resp.status_code == 200
    san_data = san_resp.json()
    assert san_data["placeholders_count"] == 3
    assert "钱八" not in san_data["sanitized_text"]
    assert "13511119999" not in san_data["sanitized_text"]
    assert "110101198506051234" not in san_data["sanitized_text"]

    # Locate placeholder for name
    name_placeholder = next(
        m["placeholder"] for m in san_data["entities_detected"] if m["entity_type"] == "chinese_name"
    )

    # 2. Desanitize inbound response
    desan_payload = {
        "text": f"已将审核通知发送给 {name_placeholder} 老师。",
        "session_id": session_id,
    }
    desan_resp = client.post("/api/v1/security/pii-vault/desanitize", json=desan_payload)
    assert desan_resp.status_code == 200
    desan_data = desan_resp.json()
    assert desan_data["restored_count"] == 1
    assert "钱八" in desan_data["restored_text"]
    assert name_placeholder not in desan_data["restored_text"]

    # 3. Clear session vault
    clear_resp = client.delete(f"/api/v1/security/pii-vault/session/{session_id}")
    assert clear_resp.status_code == 200
    assert clear_resp.json()["cleared"] is True
