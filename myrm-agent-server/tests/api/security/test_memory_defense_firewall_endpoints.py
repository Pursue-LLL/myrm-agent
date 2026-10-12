"""API endpoint tests for Memory Defense Ingestion Firewall and PII Sanitization Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.memory_defense_firewall_router import (
    router as memory_defense_firewall_router,
)
from app.services.security.memory_defense_firewall_service import (
    MemoryDefenseFirewallService,
    get_memory_defense_firewall_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = MemoryDefenseFirewallService()
    app = FastAPI()
    app.include_router(memory_defense_firewall_router)
    app.dependency_overrides[get_memory_defense_firewall_service] = lambda: test_service
    return TestClient(app)


def test_inspect_endpoint_clean_and_redact(client: TestClient) -> None:
    # 1. Clean text -> ALLOW
    resp_clean = client.post(
        "/security/memory-defense/inspect",
        json={"text": "Clean note without secrets", "default_action": "REDACT"},
    )
    assert resp_clean.status_code == 200
    data_clean = resp_clean.json()
    assert data_clean["action_taken"] == "ALLOW"
    assert data_clean["is_admitted"] is True
    assert data_clean["sanitized_text"] == "Clean note without secrets"

    # 2. Text with secret -> REDACT
    secret_text = "Here is my key: sk-ant-1234567890abcdef1234567890abcdef1234567890 for Claude."
    resp_redact = client.post(
        "/security/memory-defense/inspect",
        json={"text": secret_text, "default_action": "REDACT"},
    )
    assert resp_redact.status_code == 200
    data_redact = resp_redact.json()
    assert data_redact["action_taken"] == "REDACT"
    assert data_redact["is_admitted"] is True
    assert "[REDACTED_ANTHROPIC_KEY]" in data_redact["sanitized_text"]
    assert "sk-ant-" not in data_redact["sanitized_text"]


def test_inspect_endpoint_block_mode(client: TestClient) -> None:
    rsa_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0...\n-----END RSA PRIVATE KEY-----"
    resp_block = client.post(
        "/security/memory-defense/inspect",
        json={"text": rsa_key, "default_action": "BLOCK"},
    )
    assert resp_block.status_code == 200
    data_block = resp_block.json()
    assert data_block["action_taken"] == "BLOCK"
    assert data_block["is_admitted"] is False
    assert data_block["sanitized_text"] == ""


def test_exemptions_endpoints_lifecycle(client: TestClient) -> None:
    token = "ghp_222233334444555566667777888899990000"

    # 1. Add exemption
    resp_add = client.post(
        "/security/memory-defense/exemptions",
        json={"token_or_content": token},
    )
    assert resp_add.status_code == 200
    assert resp_add.json()["success"] is True

    # 2. List exemptions
    resp_list = client.get("/security/memory-defense/exemptions")
    assert resp_list.status_code == 200
    assert token in resp_list.json()["exemptions"]

    # 3. Check text with exempted token is ALLOWed
    resp_inspect = client.post(
        "/security/memory-defense/inspect",
        json={"text": f"Docs: {token}"},
    )
    assert resp_inspect.status_code == 200
    assert resp_inspect.json()["action_taken"] == "ALLOW"

    # 4. Delete exemption
    resp_del = client.delete(f"/security/memory-defense/exemptions?token_or_content={token}")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True


def test_catalog_and_audit_endpoints(client: TestClient) -> None:
    # 1. Get pattern catalog
    resp_cat = client.get("/security/memory-defense/catalog")
    assert resp_cat.status_code == 200
    data_cat = resp_cat.json()
    assert data_cat["total_count"] >= 40
    assert len(data_cat["patterns"]) == data_cat["total_count"]

    # 2. Inspect to generate audit record
    client.post(
        "/security/memory-defense/inspect",
        json={"text": "Audit trail test line"},
    )

    # 3. Query audit records
    resp_audit = client.get("/security/memory-defense/audit-records?limit=10")
    assert resp_audit.status_code == 200
    records = resp_audit.json()
    assert len(records) >= 1
    assert records[-1]["action_taken"] == "ALLOW"
