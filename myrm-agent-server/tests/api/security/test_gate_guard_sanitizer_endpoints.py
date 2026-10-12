"""Integration tests for GateGuard invisible Unicode sanitization API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/gate-guard-sanitizer/* endpoints.

[OUTPUT]
- Verified JSON responses matching gate guard sanitization DTO schemas.

[POS]
- Server integration test layer for denial path Unicode sanitization.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.gate_guard_sanitizer_router import (
    router as gate_guard_sanitizer_router,
)
from app.services.security.gate_guard_sanitizer_service import (
    GateGuardSanitizerService,
    get_gate_guard_sanitizer_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> GateGuardSanitizerService:
    """Fixture providing isolated in-memory service instance."""
    return GateGuardSanitizerService()


@pytest.fixture(scope="function")
def client(isolated_service: GateGuardSanitizerService) -> TestClient:
    """Fixture providing test client mounting gate_guard_sanitizer_router."""
    test_app = FastAPI(title="Gate Guard Sanitizer Test App")
    test_app.dependency_overrides[get_gate_guard_sanitizer_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        gate_guard_sanitizer_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_sanitize_path_endpoint(client: TestClient) -> None:
    payload = {
        "path": "/src/eu2028\u2028eu2029\u2029app.js\u200bhidden\u2060name\ufefftail\u3164x\u0091c1.js",
        "max_length": 500,
    }
    resp = client.post(
        "/api/v1/security/gate-guard-sanitizer/sanitize-path",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_modifications"] is True
    assert data["characters_removed_count"] >= 7
    for bad in ["\u2028", "\u2029", "\u200b", "\u2060", "\ufeff", "\u3164", "\u0091"]:
        assert bad not in data["sanitized_text"]
    assert "app.js" in data["sanitized_text"]
    assert "line_separator" in data["categories_detected"]


def test_sanitize_reason_endpoint(client: TestClient) -> None:
    payload = {
        "reason": "Permission denied: access to \u202epayload.sh blocked",
        "max_length": 1000,
    }
    resp = client.post(
        "/api/v1/security/gate-guard-sanitizer/sanitize-reason",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_modifications"] is True
    assert "\u202e" not in data["sanitized_text"]
    assert "bidi_control" in data["categories_detected"]


def test_sanitize_payload_endpoint(client: TestClient) -> None:
    payload = {
        "tool_name": "Edit\u200bFile",
        "target_path": "/var/log/\u200bauth.log",
        "reason": "Denied due to \u202eoverride pattern",
    }
    resp = client.post(
        "/api/v1/security/gate-guard-sanitizer/sanitize-payload",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_modifications"] is True
    assert data["tool_name"] == "Edit File"
    assert data["target_path"] == "/var/log/ auth.log"
    assert "\u202e" not in data["reason"]


def test_policy_summary_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/security/gate-guard-sanitizer/policy")
    assert resp.status_code == 200
    data = resp.json()
    assert data["replacement_char"] == " "
    assert data["max_path_length"] == 500
    assert data["max_reason_length"] == 1000
    assert len(data["supported_categories"]) >= 10
    assert "zero_width" in data["supported_categories"]
    assert "line_separator" in data["supported_categories"]
