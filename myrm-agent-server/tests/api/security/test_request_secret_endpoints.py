"""
[POS] tests/api/security/test_request_secret_endpoints.py
[INPUT] app.api.security.request_secret_router, app.services.security.request_secret_service
[OUTPUT] Integration tests for Request-Secret Masked Credential Card REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.request_secret_router import router as request_secret_router
from app.services.security.request_secret_service import (
    RequestSecretService,
    get_request_secret_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = RequestSecretService()
    app = FastAPI()
    app.include_router(request_secret_router)
    app.dependency_overrides[get_request_secret_service] = lambda: service
    return TestClient(app)


def test_endpoint_create_and_fulfill_lifecycle(client: TestClient) -> None:
    # 1. Create card
    create_resp = client.post(
        "/request-secret/create",
        json={
            "agent_id": "agent-worker-01",
            "task_id": "task-test-01",
            "intent": {
                "target_system": "openai",
                "purpose_description": "Fetch embeddings",
                "scope": "api_key",
                "ttl_seconds": 1800,
            },
        },
    )
    assert create_resp.status_code == 200
    card_data = create_resp.json()
    card_id = card_data["card_id"]
    assert card_data["status"] == "pending"
    assert card_data["intent"]["target_system"] == "openai"

    # 2. Fulfill card
    fulfill_resp = client.post(
        "/request-secret/fulfill",
        json={
            "card_id": card_id,
            "submission": {
                "raw_secret": "sk-live-super-secret-key-11223344",
                "extra_metadata": {"environment": "test"},
            },
        },
    )
    assert fulfill_resp.status_code == 200
    res_data = fulfill_resp.json()
    assert res_data["card_id"] == card_id
    assert res_data["target_system"] == "openai"
    assert res_data["is_backfill"] is False
    assert "sk-****3344" in res_data["mask_preview"]
    assert "sk-live-super-secret-key" not in res_data["transcript_safe_summary"]
    assert "sk-****3344" in res_data["transcript_safe_summary"]

    # 3. Query card details
    get_resp = client.get(f"/request-secret/card/{card_id}")
    assert get_resp.status_code == 200
    queried_data = get_resp.json()
    assert queried_data["status"] == "fulfilled"
    assert queried_data["masked_ref"]["mask_preview"] == res_data["mask_preview"]


def test_endpoint_backfill_and_mismatch_error(client: TestClient) -> None:
    # 1. Register saved credential
    reg_resp = client.post(
        "/request-secret/saved/register",
        json={
            "target_system": "github",
            "raw_secret": "ghp_abcdef1234567890abcdef1234567890",
        },
    )
    assert reg_resp.status_code == 200
    cred_id = reg_resp.json()["credential_id"]

    # 2. Create card for github
    create_resp = client.post(
        "/request-secret/create",
        json={
            "agent_id": "agent-git",
            "task_id": "task-git-sync",
            "intent": {
                "target_system": "github",
                "purpose_description": "Clone private repo",
            },
        },
    )
    card_id = create_resp.json()["card_id"]

    # 3. Fulfill with saved credential
    fulfill_resp = client.post(
        "/request-secret/fulfill",
        json={
            "card_id": card_id,
            "submission": {"selected_credential_id": cred_id},
        },
    )
    assert fulfill_resp.status_code == 200
    assert fulfill_resp.json()["is_backfill"] is True
    assert fulfill_resp.json()["target_system"] == "github"

    # 4. Create card for stripe and attempt using github credential -> 400
    stripe_card_resp = client.post(
        "/request-secret/create",
        json={
            "agent_id": "agent-pay",
            "task_id": "task-stripe",
            "intent": {
                "target_system": "stripe",
                "purpose_description": "Charge card",
            },
        },
    )
    stripe_card_id = stripe_card_resp.json()["card_id"]

    mismatch_resp = client.post(
        "/request-secret/fulfill",
        json={
            "card_id": stripe_card_id,
            "submission": {"selected_credential_id": cred_id},
        },
    )
    assert mismatch_resp.status_code == 400
    assert "does not match requested 'stripe'" in mismatch_resp.json()["detail"]


def test_endpoint_reject_card(client: TestClient) -> None:
    create_resp = client.post(
        "/request-secret/create",
        json={
            "agent_id": "agent-01",
            "task_id": "task-01",
            "intent": {
                "target_system": "aws",
                "purpose_description": "Access S3 bucket",
            },
        },
    )
    card_id = create_resp.json()["card_id"]

    reject_resp = client.post(
        "/request-secret/reject",
        json={"card_id": card_id, "reason": "User rejected access"},
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["status"] == "rejected"
    assert reject_resp.json()["rejection_reason"] == "User rejected access"

    # Fulfill on rejected card -> 400
    fail_fulfill = client.post(
        "/request-secret/fulfill",
        json={"card_id": card_id, "submission": {"raw_secret": "valid_token_123"}},
    )
    assert fail_fulfill.status_code == 400


def test_endpoint_saved_credentials_list(client: TestClient) -> None:
    client.post(
        "/request-secret/saved/register",
        json={"target_system": "slack", "raw_secret": "xoxb-998877665544"},
    )
    list_resp = client.get("/request-secret/saved/list?target_system=slack")
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert len(data) == 1
    assert data[0]["target_system"] == "slack"
