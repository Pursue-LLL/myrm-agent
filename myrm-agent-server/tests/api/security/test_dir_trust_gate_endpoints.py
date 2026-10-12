"""Tests for Directory Trust Gate endpoints."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.dir_trust_gate import DirectoryTrustStore

from app.api.security.dir_trust_gate_router import (
    router as dir_trust_gate_router,
)
from app.services.security.dir_trust_gate_service import (
    DirTrustGateService,
    get_dir_trust_gate_service,
)


@pytest.fixture
def test_client(tmp_path: Path) -> TestClient:
    app = FastAPI()
    custom_store = DirectoryTrustStore(storage_path=tmp_path / "trust.json")
    custom_service = DirTrustGateService(trust_store=custom_store)

    app.dependency_overrides[get_dir_trust_gate_service] = lambda: custom_service
    app.include_router(dir_trust_gate_router, prefix="/api/v1/security")

    return TestClient(app)


def test_dir_trust_gate_lifecycle_and_evaluation(test_client: TestClient) -> None:
    test_dir = "/tmp/test-cloned-repo"

    # 1. Initially untrusted repo with remote URL and token
    eval_resp = test_client.post(
        "/api/v1/security/dir-trust-gate/evaluate",
        json={
            "directory": test_dir,
            "remote_url": "https://attacker.site/steal",
            "remote_token": "secret_token_123",
            "scope": "my-team",
        },
    )
    assert eval_resp.status_code == 200
    data = eval_resp.json()
    assert data["is_trusted"] is False
    assert data["is_remote_allowed"] is False
    assert data["allowed_remote_url"] is None
    assert data["allowed_remote_token"] is None
    assert data["effective_scope"] == "my-team"
    assert "were dropped to prevent credential exfiltration" in data["warning_message"]

    # 2. Trust the directory
    trust_resp = test_client.post(
        "/api/v1/security/dir-trust-gate/trust",
        json={"directory": test_dir, "reason": "Authorized by test"},
    )
    assert trust_resp.status_code == 200
    t_data = trust_resp.json()
    assert t_data["is_trusted"] is True
    assert t_data["action"] == "trust"

    # 3. Check list contains directory
    list_resp = test_client.get("/api/v1/security/dir-trust-gate/list")
    assert list_resp.status_code == 200
    l_data = list_resp.json()
    assert any(test_dir in d for d in l_data["trusted_directories"])

    # 4. Evaluate again - now trusted and allowed
    eval_resp_2 = test_client.post(
        "/api/v1/security/dir-trust-gate/evaluate",
        json={
            "directory": test_dir,
            "remote_url": "https://api.myrm.io/sync",
            "remote_token": "valid_token",
            "scope": "my-team",
        },
    )
    assert eval_resp_2.status_code == 200
    d2 = eval_resp_2.json()
    assert d2["is_trusted"] is True
    assert d2["is_remote_allowed"] is True
    assert d2["allowed_remote_url"] == "https://api.myrm.io/sync"
    assert d2["allowed_remote_token"] == "valid_token"
    assert d2["warning_message"] is None

    # 5. Untrust directory
    untrust_resp = test_client.post(
        "/api/v1/security/dir-trust-gate/untrust",
        json={"directory": test_dir},
    )
    assert untrust_resp.status_code == 200
    assert untrust_resp.json()["is_trusted"] is False
