"""
[POS] tests/api/security/test_blast_radius_approval_endpoints.py
Integration tests for Blast Radius Dry-Run Impact Preview & Typed Launch Codes REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.blast_radius_approval_router import (
    router as blast_radius_approval_router,
)
from app.services.security.blast_radius_approval_service import (
    BlastRadiusApprovalService,
    get_blast_radius_approval_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = BlastRadiusApprovalService()
    app = FastAPI()
    app.include_router(blast_radius_approval_router)
    app.dependency_overrides[get_blast_radius_approval_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_single_command(client: TestClient) -> None:
    # 1. Non-destructive command
    resp_safe = client.post(
        "/blast-radius-approval/evaluate",
        json={"command": "npm test", "span_id": "test-span-01"},
    )
    assert resp_safe.status_code == 200
    safe_data = resp_safe.json()
    assert safe_data["span_id"] == "test-span-01"
    assert safe_data["is_destructive"] is False
    assert safe_data["never_folded"] is False
    assert safe_data["impact_preview"] is None
    assert "Enter" in safe_data["allowed_shortcuts"]

    # 2. Destructive command requiring launch code
    resp_dest = client.post(
        "/blast-radius-approval/evaluate",
        json={"command": "rm -rf /var/log/app/*.log", "span_id": "test-span-02"},
    )
    assert resp_dest.status_code == 200
    dest_data = resp_dest.json()
    assert dest_data["span_id"] == "test-span-02"
    assert dest_data["is_destructive"] is True
    assert dest_data["never_folded"] is True
    assert dest_data["impact_preview"] is not None
    assert dest_data["launch_code"] is not None
    assert dest_data["launch_code"]["requires_challenge"] is True
    assert "Enter" not in dest_data["allowed_shortcuts"]


def test_endpoint_batch_evaluate(client: TestClient) -> None:
    resp = client.post(
        "/blast-radius-approval/batch-evaluate",
        json={
            "commands": [
                {"span_id": "s1", "command": "cat config.json"},
                {"span_id": "s2", "command": "git push --force origin main"},
                {"span_id": "s3", "command": "echo done"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["policies"]) == 3
    # High-risk force push is never folded and forms an isolated group
    assert ["s2"] in data["decision_groups"]
    assert ["s1", "s3"] in data["decision_groups"]


def test_endpoint_verify_launch_code_lifecycle(client: TestClient) -> None:
    # Issue a challenge first
    eval_resp = client.post(
        "/blast-radius-approval/evaluate",
        json={"command": "vercel --prod", "span_id": "deploy-01"},
    )
    token = eval_resp.json()["launch_code"]["challenge_token"]
    assert token is not None

    # Verify with wrong code
    fail_resp = client.post(
        "/blast-radius-approval/verify-launch-code",
        json={"token": token, "user_input": "000000"},
    )
    assert fail_resp.status_code == 200
    assert fail_resp.json()["is_valid"] is False

    # Verify with correct code
    succ_resp = client.post(
        "/blast-radius-approval/verify-launch-code",
        json={"token": token, "user_input": token},
    )
    assert succ_resp.status_code == 200
    assert succ_resp.json()["is_valid"] is True

    # Replay attempt fails
    replay_resp = client.post(
        "/blast-radius-approval/verify-launch-code",
        json={"token": token, "user_input": token},
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["is_valid"] is False
    assert "already been consumed" in replay_resp.json()["reason"].lower()
