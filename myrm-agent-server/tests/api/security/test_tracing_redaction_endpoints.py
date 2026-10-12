"""API endpoint tests for Tracing Sensitive Data Redactor in myrm-agent-server."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.tracing_redaction_router import (
    router as tracing_redaction_router,
)
from app.services.security.tracing_redaction_service import (
    TracingRedactionService,
    get_tracing_redaction_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    service = TracingRedactionService()
    app.dependency_overrides[get_tracing_redaction_service] = lambda: service
    app.include_router(tracing_redaction_router, prefix="/api/v1/security")
    return TestClient(app)


def test_post_sanitize_trace_span_endpoint(client: TestClient) -> None:
    payload = {
        "trace_id": "api_trace_101",
        "span_id": "api_span_101",
        "path_type": "success",
        "payload": {
            "api_key": "sk-proj-987654321098765432109876",
            "password": "secret_password_here",
            "log": "Token is Bearer my-auth-token-12345678",
            "status": "ok",
        },
        "raw_error": "Connection error with sk-proj-987654321098765432109876",
        "opt_out_requested": False,
    }

    response = client.post(
        "/api/v1/security/tracing-redaction/sanitize-span", json=payload
    )
    assert response.status_code == 200
    data = response.json()

    assert data["trace_id"] == "api_trace_101"
    assert data["span_id"] == "api_span_101"
    assert data["path_type"] == "success"
    assert data["is_dropped"] is False
    assert data["redaction_count"] > 0
    assert data["policy_applied"] == "redaction_enforced"

    sanitized_payload = data["sanitized_payload"]
    assert sanitized_payload["api_key"] == "[REDACTED_SENSITIVE_FIELD]"
    assert sanitized_payload["password"] == "[REDACTED_SENSITIVE_FIELD]"
    assert "Bearer [REDACTED_TOKEN]" in sanitized_payload["log"]
    assert sanitized_payload["status"] == "ok"

    assert data["sanitized_error"] is not None
    assert "sk-proj-" not in data["sanitized_error"]
    assert "[REDACTED_API_KEY]" in data["sanitized_error"]


def test_post_sanitize_trace_span_drop_opt_out(client: TestClient) -> None:
    payload = {
        "trace_id": "api_trace_102",
        "span_id": "api_span_102",
        "path_type": "streaming",
        "payload": {"private_message": "confidential streaming content"},
        "opt_out_requested": True,
        "opt_out_mode": "drop_trace",
    }

    response = client.post(
        "/api/v1/security/tracing-redaction/sanitize-span", json=payload
    )
    assert response.status_code == 200
    data = response.json()

    assert data["is_dropped"] is True
    assert data["sanitized_payload"] == {}
    assert data["sanitized_error"] is None
    assert data["policy_applied"] == "opt_out_drop"


def test_get_opt_out_modes_endpoint(client: TestClient) -> None:
    response = client.get("/api/v1/security/tracing-redaction/opt-out-modes")
    assert response.status_code == 200
    data = response.json()

    assert "available_opt_out_modes" in data
    assert "drop_trace" in data["available_opt_out_modes"]
    assert "redact_mandatory" in data["available_opt_out_modes"]
    assert "allow_tracing" in data["available_opt_out_modes"]

    assert "supported_execution_paths" in data
    assert "success" in data["supported_execution_paths"]
    assert "error" in data["supported_execution_paths"]
    assert "streaming" in data["supported_execution_paths"]
    assert "retry" in data["supported_execution_paths"]
    assert "resume" in data["supported_execution_paths"]
