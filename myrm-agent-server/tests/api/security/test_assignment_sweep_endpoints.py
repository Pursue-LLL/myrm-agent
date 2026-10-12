"""
[POS] tests/api/security/test_assignment_sweep_endpoints.py
[INPUT] app.api.security.assignment_sweep_router, app.services.security.assignment_sweep_service
[OUTPUT] Integration tests for Quoted-Key Secret Assignment Sweep REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.assignment_sweep_router import router as assignment_sweep_router
from app.services.security.assignment_sweep_service import (
    AssignmentSweepService,
    get_assignment_sweep_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = AssignmentSweepService()
    app = FastAPI()
    app.include_router(assignment_sweep_router)
    app.dependency_overrides[get_assignment_sweep_service] = lambda: service
    return TestClient(app)


def test_endpoint_sweep_quoted_secrets(client: TestClient) -> None:
    resp = client.post(
        "/assignment-sweep/sweep",
        json={
            "content": (
                '{\n  "api_key": "sk-secret-token-abcdef123456",\n'
                '  "client_secret": "my-client-secret-998877"\n}'
            )
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "suspected_leak"
    assert data["active_leaks_count"] == 2
    assert len(data["findings"]) == 2
    keys = {f["key_name"] for f in data["findings"]}
    assert "api_key" in keys
    assert "client_secret" in keys


def test_endpoint_sweep_benign_alphanumeric_words(client: TestClient) -> None:
    resp = client.post(
        "/assignment-sweep/sweep",
        json={
            "content": (
                "tokenizer = AutoTokenizer.from_pretrained('gpt2')\n"
                "secretive = False\n"
                "token_count = 100\n"
                "credentials_file = '/path/to/cache'\n"
            )
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verdict"] == "clean"
    assert data["active_leaks_count"] == 0
    assert len(data["findings"]) == 0


def test_endpoint_audit_dsn_loopback_vs_remote(client: TestClient) -> None:
    # 1. Localhost DSN with default credentials -> Exempted
    resp_local = client.post(
        "/assignment-sweep/audit-dsn",
        json={"raw_url": "postgresql://postgres:postgres@localhost:5432/my_dev_db"},
    )
    assert resp_local.status_code == 200
    data_local = resp_local.json()
    assert data_local["is_loopback"] is True
    assert data_local["is_exempt"] is True

    # 2. Remote/compose service DSN with default credentials -> Must NOT be exempted
    resp_compose = client.post(
        "/assignment-sweep/audit-dsn",
        json={"raw_url": "postgresql://postgres:postgres@db:5432/prod_db"},
    )
    assert resp_compose.status_code == 200
    data_compose = resp_compose.json()
    assert data_compose["is_loopback"] is False
    assert data_compose["is_exempt"] is False


def test_endpoint_check_clean(client: TestClient) -> None:
    # Clean check
    clean_resp = client.post(
        "/assignment-sweep/check-clean",
        json={"content": "const serverPort = 8080;\nconst appEnv = 'production';"},
    )
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()
    assert clean_data["is_clean"] is True
    assert clean_data["active_leaks_count"] == 0

    # Dirty check
    dirty_resp = client.post(
        "/assignment-sweep/check-clean",
        json={"content": "export PRIVATE_KEY='-----BEGIN RSA PRIVATE KEY-----'"},
    )
    assert dirty_resp.status_code == 200
    dirty_data = dirty_resp.json()
    assert dirty_data["is_clean"] is False
    assert dirty_data["active_leaks_count"] >= 1
