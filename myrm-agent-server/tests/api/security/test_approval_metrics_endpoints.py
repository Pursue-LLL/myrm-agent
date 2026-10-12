"""Integration tests for Approval False Positive Metric Loop API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.approval_metrics_router import (
    router as approval_metrics_router,
)
from app.services.security.approval_metrics_service import (
    ApprovalMetricsService,
    get_approval_metrics_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> ApprovalMetricsService:
    """Fixture providing isolated in-memory service."""
    return ApprovalMetricsService(default_alert_threshold=0.05)


@pytest.fixture(scope="function")
def client(isolated_service: ApprovalMetricsService) -> TestClient:
    """Fixture providing test client mounting approval_metrics_router."""
    test_app = FastAPI(title="Approval Metrics Test App")
    test_app.dependency_overrides[get_approval_metrics_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        approval_metrics_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_verdict_recording_and_feedback_flow(client: TestClient) -> None:
    # 1. Record verdict
    rec_payload = {
        "command": "git push --force origin main",
        "decision": "deny",
        "reason": "Force pushing to main branch is strictly blocked",
        "workspace_root": "/workspace/app",
        "taint_labels": ["GIT_ADMIN"],
    }
    rec_resp = client.post(
        "/api/v1/security/approval-metrics/verdict",
        json=rec_payload,
    )
    assert rec_resp.status_code == 200
    rec_data = rec_resp.json()
    assert rec_data["decision"] == "deny"
    audit_id = rec_data["audit_id"]

    # 2. Submit feedback: confirmed true positive
    fb_payload = {
        "audit_id": audit_id,
        "feedback": "true_positive",
        "feedback_reason": "Accidental command execution caught by safety classifier",
    }
    fb_resp = client.post(
        "/api/v1/security/approval-metrics/feedback",
        json=fb_payload,
    )
    assert fb_resp.status_code == 200
    assert fb_resp.json()["success"] is True

    # 3. Query metrics
    metrics_resp = client.get(
        "/api/v1/security/approval-metrics/metrics?window_seconds=3600"
    )
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert metrics_data["total_evaluations"] == 1
    assert metrics_data["total_blocks_or_asks"] == 1
    assert metrics_data["confirmed_false_positives"] == 0
    assert metrics_data["confirmed_true_positives"] == 1
    assert metrics_data["false_positive_rate"] == 0.0
    assert metrics_data["is_alerting"] is False


def test_false_positive_alert_and_samples_export(client: TestClient) -> None:
    # 1. Record false positive
    rec_resp = client.post(
        "/api/v1/security/approval-metrics/verdict",
        json={
            "command": "pnpm build",
            "decision": "uncertain",
            "reason": "Uncertain if build output modifies shared assets",
        },
    )
    audit_id = rec_resp.json()["audit_id"]

    # 2. Submit feedback marking as false positive
    client.post(
        "/api/v1/security/approval-metrics/feedback",
        json={
            "audit_id": audit_id,
            "feedback": "false_positive",
            "feedback_reason": "Standard frontend build command",
        },
    )

    # 3. Check metrics (alert triggered because threshold is 0.05 and FPR is 1.0)
    metrics_resp = client.get(
        "/api/v1/security/approval-metrics/metrics?window_seconds=3600"
    )
    assert metrics_resp.status_code == 200
    metrics_data = metrics_resp.json()
    assert metrics_data["total_blocks_or_asks"] == 1
    assert metrics_data["confirmed_false_positives"] == 1
    assert metrics_data["false_positive_rate"] == 1.0
    assert metrics_data["is_alerting"] is True

    # 4. Export samples
    samples_resp = client.get(
        "/api/v1/security/approval-metrics/samples/false-positives?limit=10"
    )
    assert samples_resp.status_code == 200
    samples_data = samples_resp.json()
    assert samples_data["total_count"] == 1
    sample = samples_data["samples"][0]
    assert sample["command"] == "pnpm build"
    assert "ALLOW EXCEPTIONS" in sample["suggested_rule_tuning"]
