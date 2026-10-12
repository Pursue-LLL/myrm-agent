"""Integration tests for Structured JSON Scan Failure Errors API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.structured_scan_errors_router import (
    router as structured_scan_errors_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting structured_scan_errors_router."""
    test_app = FastAPI(title="Structured Scan Errors Test App")
    test_app.include_router(
        structured_scan_errors_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_emit_failure_endpoint(client: TestClient) -> None:
    payload = {
        "scan_id": "scan-api-101",
        "target_path_or_url": "https://github.com/my-org/core-agent",
        "scanner_engine": "osv-scanner",
        "exit_code": 127,
        "stderr": "sh: osv-scanner: command not found in /usr/local/bin",
        "metadata": {"runner": "k8s-pod-77"},
    }
    resp = client.post(
        "/api/v1/security/structured-scan-errors/emit-failure",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error_code"] == "SCAN_ENGINE_CRASH"
    assert data["severity"] == "CRITICAL"
    assert data["remediation"]["suggested_action"] == "BLOCK_PIPELINE"
    assert data["context"]["scan_id"] == "scan-api-101"
    assert data["context"]["metadata"]["runner"] == "k8s-pod-77"


def test_classify_failure_endpoint(client: TestClient) -> None:
    payload = {
        "exit_code": 1,
        "stderr": "HTTP 429 Too Many Requests: Rate limit exceeded for vulnerability database",
    }
    resp = client.post(
        "/api/v1/security/structured-scan-errors/classify-failure",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["error_code"] == "SCAN_RATE_LIMITED"
    assert data["suggested_action"] == "RETRY"
    assert data["retryable"] is True
    assert data["backoff_seconds"] == 60.0
