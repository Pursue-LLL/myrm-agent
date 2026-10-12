"""Integration tests for Credential Stdin Pipelining & Process Leakage Shield API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.credential_shield_router import (
    router as credential_shield_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting credential_shield_router."""
    test_app = FastAPI(title="Credential Shield Test App")
    test_app.include_router(credential_shield_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_analyze_command_endpoint(client: TestClient) -> None:
    # 1. Safe command
    safe_payload = {"command": "curl -sS https://api.myrm.dev/ping"}
    resp_safe = client.post("/api/v1/security/credential-shield/analyze", json=safe_payload)
    assert resp_safe.status_code == 200
    safe_data = resp_safe.json()
    assert safe_data["is_safe_for_process_table"] is True
    assert safe_data["risk_level"] == "SAFE"

    # 2. Leaking command
    leaking_payload = {
        "command": "curl -H 'Authorization: Bearer secret_live_token' https://api.myrm.dev/v1"
    }
    resp_leak = client.post("/api/v1/security/credential-shield/analyze", json=leaking_payload)
    assert resp_leak.status_code == 200
    leak_data = resp_leak.json()
    assert leak_data["is_safe_for_process_table"] is False
    assert leak_data["risk_level"] == "HIGH_RISK_PROCESS_TABLE_EXPOSURE"
    assert "HTTP_AUTH_HEADER_DETECTED" in leak_data["detected_leaks"]


def test_pipeline_and_sanitize_endpoints(client: TestClient) -> None:
    # 1. Pipeline command
    pipeline_payload = {
        "command": "curl -sS -H 'Authorization: Bearer secret_live_token' https://api.myrm.dev/v1"
    }
    resp_pipe = client.post("/api/v1/security/credential-shield/pipeline", json=pipeline_payload)
    assert resp_pipe.status_code == 200
    pipe_data = resp_pipe.json()
    assert pipe_data["transport_mode"] == "STDIN_CONFIG_STREAM"
    assert pipe_data["has_stdin_payload"] is True
    assert "-K" in pipe_data["sanitized_argv"]
    assert "secret_live_token" not in " ".join(pipe_data["sanitized_argv"])

    # 2. Sanitize display command
    sanitize_payload = {
        "command": "curl -H 'Authorization: Bearer secret_token' --api-key apikey_9988 https://example.com"
    }
    resp_sanitize = client.post(
        "/api/v1/security/credential-shield/sanitize-display", json=sanitize_payload
    )
    assert resp_sanitize.status_code == 200
    sanitized_data = resp_sanitize.json()
    assert "secret_token" not in sanitized_data["sanitized_command"]
    assert "[REDACTED_CREDENTIAL]" in sanitized_data["sanitized_command"]
