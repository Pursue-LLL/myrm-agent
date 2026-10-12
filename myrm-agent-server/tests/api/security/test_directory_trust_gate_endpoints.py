"""API endpoint tests for Directory Trust Gate in myrm-agent-server."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.directory_trust_gate import DirectoryTrustStore

from app.api.security.directory_trust_gate_router import (
    router as directory_trust_gate_router,
)
from app.services.security.directory_trust_gate_service import (
    DirectoryTrustGateService,
    get_directory_trust_gate_service,
)


@pytest.fixture
def temp_dir() -> str:
    with tempfile.TemporaryDirectory() as td:
        yield td


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    trust_store = DirectoryTrustStore()
    service = DirectoryTrustGateService(trust_store=trust_store)

    app.dependency_overrides[get_directory_trust_gate_service] = lambda: service
    app.include_router(directory_trust_gate_router, prefix="/api/v1/security")
    return TestClient(app)


def test_trust_and_list_directories_api(client: TestClient, temp_dir: str) -> None:
    project_path = str(Path(temp_dir) / "demo_repo")
    Path(project_path).mkdir(parents=True, exist_ok=True)

    # 1. Trust
    resp = client.post(
        "/api/v1/security/directory-trust-gate/trust",
        json={"directory": project_path},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["trusted"] is True
    assert data["canonical_path"] == str(Path(project_path).resolve())

    # 2. List
    list_resp = client.get("/api/v1/security/directory-trust-gate/trusted")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["count"] >= 1
    assert data["canonical_path"] in list_data["trusted_directories"]

    # 3. Untrust
    untrust_resp = client.post(
        "/api/v1/security/directory-trust-gate/untrust",
        json={"directory": project_path},
    )
    assert untrust_resp.status_code == 200
    assert untrust_resp.json()["removed"] is True


def test_resolve_untrusted_drops_remote_api(client: TestClient, temp_dir: str) -> None:
    untrusted_repo = str(Path(temp_dir) / "cloned_repo_api")
    Path(untrusted_repo).mkdir(parents=True, exist_ok=True)

    payload = {
        "start_directory": untrusted_repo,
        "config_override": {
            "scope": "test_scope",
            "remote_url": "https://malicious.org/exfiltrate",
            "remote_token": "bearer-stolen-token",
        },
    }

    resp = client.post(
        "/api/v1/security/directory-trust-gate/resolve", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["is_directory_trusted"] is False
    assert data["decision"] == "UNTRUSTED_REMOTE_REFUSED"
    assert data["remote_url"] is None
    assert data["remote_token"] is None
    assert data["refusal_notice"] is not None
    assert "[MYRM_SECURITY]" in data["refusal_notice"]


def test_resolve_trusted_allows_remote_api(client: TestClient, temp_dir: str) -> None:
    trusted_repo = str(Path(temp_dir) / "trusted_repo_api")
    Path(trusted_repo).mkdir(parents=True, exist_ok=True)

    # Trust first
    client.post(
        "/api/v1/security/directory-trust-gate/trust",
        json={"directory": trusted_repo},
    )

    payload = {
        "start_directory": trusted_repo,
        "config_override": {
            "scope": "corp_scope",
            "remote_url": "https://vault.internal/sync",
            "remote_token": "valid_corp_token",
        },
    }

    resp = client.post(
        "/api/v1/security/directory-trust-gate/resolve", json=payload
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["is_directory_trusted"] is True
    assert data["decision"] == "TRUSTED_AUTHORIZED"
    assert data["remote_url"] == "https://vault.internal/sync"
    assert data["remote_token"] == "valid_corp_token"
    assert data["refusal_notice"] is None
