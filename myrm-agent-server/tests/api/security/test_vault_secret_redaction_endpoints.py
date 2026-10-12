"""Integration tests for Vault Secret Dynamic Redaction REST endpoints.

[POS] tests/api/security/test_vault_secret_redaction_endpoints.py
[INPUT] app.api.security.vault_secret_redaction_router, app.services.security.vault_secret_redaction_service
[OUTPUT] End-to-end integration tests for text/tool/user-message redaction,
streaming scrubbing, secret lifecycle, stats, and configuration.
Strict typing applied: No `Any` types allowed. Enforced under 400 lines limit.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.vault_secret_redaction_router import (
    get_vault_secret_redaction_service,
)
from app.api.security.vault_secret_redaction_router import (
    router as vault_secret_redaction_router,
)
from app.services.security.vault_secret_redaction_service import (
    VaultSecretRedactionService,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = VaultSecretRedactionService()
    service.clear()
    app = FastAPI()
    app.include_router(vault_secret_redaction_router, prefix="/api/security")
    app.dependency_overrides[get_vault_secret_redaction_service] = (
        lambda: service
    )
    return TestClient(app)


def test_endpoint_secret_registration_and_listing(client: TestClient) -> None:
    # 1. Register a valid secret
    payload = {
        "name": "API_SECRET_KEY",
        "value": "super_secret_endpoint_key_9999",
        "source": "dynamic_captured",
    }
    resp = client.post("/api/security/vault-redaction/secrets", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["registered"] is True
    assert data["name"] == "API_SECRET_KEY"

    # 2. List secrets
    list_resp = client.get("/api/security/vault-redaction/secrets")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert "API_SECRET_KEY" in list_data["secret_names"]
    assert list_data["total_count"] >= 1

    # 3. Unregister secret
    del_resp = client.delete(
        "/api/security/vault-redaction/secrets/API_SECRET_KEY"
    )
    assert del_resp.status_code == 200
    assert del_resp.json()["unregistered"] is True


def test_endpoint_redact_text(client: TestClient) -> None:
    # Register a secret first
    client.post(
        "/api/security/vault-redaction/secrets",
        json={
            "name": "SLACK_TOKEN",
            "value": "xoxb-secret-slack-token-12345",
        },
    )

    # Redact text
    payload = {
        "text": "Failed alerting to Slack: xoxb-secret-slack-token-12345 unauthorized"
    }
    resp = client.post(
        "/api/security/vault-redaction/redact-text", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "xoxb-secret-slack-token-12345" not in data["clean_content"]
    assert "SLACK_TOKEN=<REDACTED>" in data["clean_content"]
    assert data["redacted_count"] == 1
    assert "SLACK_TOKEN" in data["matched_secrets"]


def test_endpoint_redact_tool_return(client: TestClient) -> None:
    client.post(
        "/api/security/vault-redaction/secrets",
        json={
            "name": "DB_CRED",
            "value": "db_pass_secure_value_5432",
        },
    )

    payload = {
        "tool_name": "postgres_query",
        "output_text": "Error: Auth failed for pass db_pass_secure_value_5432",
        "metadata": {"dsn": "postgres://usr:db_pass_secure_value_5432@db:5432"},
    }
    resp = client.post(
        "/api/security/vault-redaction/redact-tool-return", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "postgres_query"
    assert "db_pass_secure_value_5432" not in data["clean_output"]
    assert "DB_CRED=<REDACTED>" in data["clean_output"]
    assert "db_pass_secure_value_5432" not in data["clean_metadata"]["dsn"]
    assert data["redacted_count"] == 2


def test_endpoint_redact_user_message(client: TestClient) -> None:
    client.post(
        "/api/security/vault-redaction/secrets",
        json={
            "name": "USER_TOKEN",
            "value": "ghp_user_private_token_9999",
        },
    )

    payload = {
        "user_id": "usr_42",
        "content": "Please deploy using ghp_user_private_token_9999",
    }
    resp = client.post(
        "/api/security/vault-redaction/redact-user-message", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "usr_42"
    assert "ghp_user_private_token_9999" not in data["clean_content"]
    assert "USER_TOKEN=<REDACTED>" in data["clean_content"]
    assert data["redacted_count"] == 1


def test_endpoint_stream_scrubbing_push_and_flush(client: TestClient) -> None:
    client.post(
        "/api/security/vault-redaction/secrets",
        json={
            "name": "STREAM_TOKEN",
            "value": "sk-stream-scrub-token-val-001",
        },
    )

    session_id = "test-session-stream-99"
    # Chunk 1
    c1_resp = client.post(
        "/api/security/vault-redaction/stream-scrub/push",
        json={
            "session_id": session_id,
            "chunk": "Here is token: sk-stream-scrub-",
        },
    )
    assert c1_resp.status_code == 200
    c1_data = c1_resp.json()
    assert c1_data["emitted_chunk"] == "Here is token: "
    assert c1_data["held_back_len"] > 0

    # Chunk 2
    c2_resp = client.post(
        "/api/security/vault-redaction/stream-scrub/push",
        json={
            "session_id": session_id,
            "chunk": "token-val-001 [END]",
        },
    )
    assert c2_resp.status_code == 200
    c2_data = c2_resp.json()
    assert "sk-stream-scrub-token-val-001" not in c2_data["emitted_chunk"]
    assert "STREAM_TOKEN=<REDACTED>" in c2_data["emitted_chunk"]
    assert "[END]" in c2_data["emitted_chunk"]

    # Flush
    f_resp = client.post(
        "/api/security/vault-redaction/stream-scrub/flush",
        json={"session_id": session_id},
    )
    assert f_resp.status_code == 200
    assert f_resp.json()["emitted_chunk"] == ""


def test_endpoint_stats_and_config(client: TestClient) -> None:
    # 1. Config GET
    cfg_resp = client.get("/api/security/vault-redaction/config")
    assert cfg_resp.status_code == 200
    cfg_data = cfg_resp.json()
    assert cfg_data["min_secret_length"] >= 3

    # 2. Config PUT
    up_resp = client.put(
        "/api/security/vault-redaction/config",
        json={"min_secret_length": 9, "mask_template": "***{name}***"},
    )
    assert up_resp.status_code == 200
    up_data = up_resp.json()
    assert up_data["min_secret_length"] == 9
    assert up_data["mask_template"] == "***{name}***"

    # 3. Stats GET
    stats_resp = client.get("/api/security/vault-redaction/stats")
    assert stats_resp.status_code == 200
    assert "stats" in stats_resp.json()
