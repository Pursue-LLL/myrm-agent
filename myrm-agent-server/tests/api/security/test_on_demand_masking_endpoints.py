"""Tests for On-Demand Credential Masking endpoints."""

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.on_demand_masking_router import (
    router as on_demand_masking_router,
)


@pytest.fixture
def test_client() -> TestClient:
    app = FastAPI()
    app.include_router(on_demand_masking_router, prefix="/api/v1/security")
    return TestClient(app)


def test_mask_text_endpoint(test_client: TestClient) -> None:
    secret = "secretToken987654321"
    b64_secret = base64.b64encode(secret.encode("utf-8")).decode("utf-8").rstrip("=")

    resp = test_client.post(
        "/api/v1/security/on-demand-masking/mask-text",
        json={
            "text": f"Found tokens raw: {secret} and b64: {b64_secret}",
            "environment": {"MY_SECRET": secret},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_redactions"] is True
    assert "MY_SECRET" in data["redacted_labels"]
    assert secret not in data["masked_text"]
    assert b64_secret not in data["masked_text"]
    assert (
        "Found tokens raw: <redacted:MY_SECRET> and b64: <redacted:MY_SECRET>"
        == data["masked_text"]
    )


def test_resolve_and_execute_endpoint(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/on-demand-masking/resolve-and-execute",
        json={
            "command": 'python3 -c \'import os; print("Token: " + os.environ.get("KEY1", "missing"))\'',
            "requested_handles": ["cred-a"],
            "mock_providers": {
                "cred-a": {"KEY1": "superSecretVal123"},
                "cred-b": {"KEY2": "unusedVal999"},
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["exit_code"] == 0
    assert "KEY1" in data["resolved_env_keys"]
    assert "KEY2" not in data["resolved_env_keys"]  # cred-b was not requested!
    assert "superSecretVal123" not in data["masked_stdout"]
    assert "Token: <redacted:KEY1>" in data["masked_stdout"]
    assert "KEY1" in data["redacted_labels"]
