"""
[POS] tests/api/security/test_execution_approval_sanitizer_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.execution_approval_sanitizer_router
[OUTPUT] Integration tests for Execution Approval Secret Redaction REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.execution_approval_sanitizer_router import (
    router as execution_approval_sanitizer_router,
)
from app.services.security.execution_approval_sanitizer_service import (
    ExecutionApprovalSanitizerService,
    get_execution_approval_sanitizer_service,
)
from tests.support.fake_secrets import slack_bot_token


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = ExecutionApprovalSanitizerService()
    app = FastAPI()
    app.include_router(execution_approval_sanitizer_router)
    app.dependency_overrides[get_execution_approval_sanitizer_service] = lambda: service
    return TestClient(app)


def test_endpoint_sanitize_approval_payload(client: TestClient) -> None:
    """Test REST endpoint sanitizing execution approval command payload."""
    raw = (
        'aws s3 sync s3://bucket . --access-key AKIAIOSFODNN7EXAMPLE '
        '&& curl -H "Authorization: Bearer secret-jwt-bearer-token-1234567890abcdef" https://api.internal'
    )

    resp = client.post(
        "/execution-approval-sanitizer/sanitize",
        json={
            "request_id": "api-redact-01",
            "session_id": "sess-api-01",
            "raw_command_or_text": raw,
            "channel_target": "webui",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "AKIAIOSFODNN7EXAMPLE" not in data["sanitized_text"]
    assert "secret-jwt-bearer-token-1234567890abcdef" not in data["sanitized_text"]
    assert "[REDACTED:AWS_KEY_ID]" in data["sanitized_text"]
    assert "Bearer [REDACTED:BEARER_TOKEN]" in data["sanitized_text"]
    assert data["redactions_count"] == 2
    assert "AWS_CREDENTIAL" in data["detected_secret_types"]
    assert "BEARER_TOKEN" in data["detected_secret_types"]
    assert len(data["findings"]) == 2


def test_endpoint_quick_sanitize(client: TestClient) -> None:
    """Test quick sanitize endpoint."""
    resp = client.post(
        "/execution-approval-sanitizer/quick-sanitize",
        json={
            "text": f"export SLACK_BOT_TOKEN={slack_bot_token('123456789012-1234567890123-abcdefghijklmnopqrstuvwx')}",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "[REDACTED:SLACK_TOKEN]" in data["sanitized_text"]
    assert data["redactions_count"] == 1
    assert "SLACK_TOKEN" in data["detected_secret_types"]


def test_endpoint_clean_payload(client: TestClient) -> None:
    """Test quick sanitize on benign payload without secrets."""
    resp = client.post(
        "/execution-approval-sanitizer/quick-sanitize",
        json={"text": "git status -s && cargo check"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["sanitized_text"] == "git status -s && cargo check"
    assert data["redactions_count"] == 0
    assert "未检测到敏感明文凭据" in data["badge_summary"]


def test_endpoint_metrics(client: TestClient) -> None:
    """Test retrieving operational metrics."""
    client.post(
        "/execution-approval-sanitizer/quick-sanitize",
        json={"text": "gh auth token ghp_123456789012345678901234567890123456"},
    )
    resp = client.get("/execution-approval-sanitizer/metrics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["payloads_evaluated_total"] >= 1
    assert data["redacted_payloads_total"] >= 1
