"""Integration tests for Directory Trust Gate and Remote Memory Resolution endpoints."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.directory_trust_remote_memory_router import (
    router as directory_trust_remote_memory_router,
)
from app.services.security.directory_trust_remote_memory_service import (
    DirectoryTrustRemoteMemoryService,
    get_directory_trust_remote_memory_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> DirectoryTrustRemoteMemoryService:
    """Fixture providing an isolated in-memory service instance."""
    return DirectoryTrustRemoteMemoryService()


@pytest.fixture(scope="function")
def client(isolated_service: DirectoryTrustRemoteMemoryService) -> TestClient:
    """Fixture providing test client mounting directory_trust_remote_memory_router."""
    test_app = FastAPI(title="Directory Trust Test App")
    test_app.dependency_overrides[get_directory_trust_remote_memory_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        directory_trust_remote_memory_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_trust_directory_endpoints(client: TestClient) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        # 1. Query check initially untrusted
        chk_resp = client.get(
            f"/api/v1/security/directory-trust-remote-memory/trust/check?directory={tmpdir}"
        )
        assert chk_resp.status_code == 200
        assert chk_resp.json()["is_trusted"] is False

        # 2. Trust directory
        trust_resp = client.post(
            "/api/v1/security/directory-trust-remote-memory/trust",
            json={"directory": tmpdir, "action": "trust"},
        )
        assert trust_resp.status_code == 200
        assert trust_resp.json()["is_trusted"] is True
        assert trust_resp.json()["action"] == "trust"

        # 3. List trusted
        list_resp = client.get(
            "/api/v1/security/directory-trust-remote-memory/trust/list"
        )
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # 4. Untrust directory
        untrust_resp = client.post(
            "/api/v1/security/directory-trust-remote-memory/trust",
            json={"directory": tmpdir, "action": "untrust"},
        )
        assert untrust_resp.status_code == 200
        assert untrust_resp.json()["is_trusted"] is False


def test_resolve_project_remote_endpoint(client: TestClient) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = os.path.join(tmpdir, ".myrm.yaml")
        resolve_payload = {
            "config": {
                "local_scope": "repo:security/infra",
                "domain": "security",
                "remote_url": "https://enterprise.plur.internal/v1",
                "remote_token": "bearer-corp-secret-999",
                "remote_scopes": ["group:security"],
            },
            "config_path": cfg_file,
        }

        # 1. Resolve from untrusted directory -> blocked
        resp_untrusted = client.post(
            "/api/v1/security/directory-trust-remote-memory/resolve",
            json=resolve_payload,
        )
        assert resp_untrusted.status_code == 200
        data_untrusted = resp_untrusted.json()
        assert data_untrusted["is_trusted"] is False
        assert data_untrusted["is_outbound_authorized"] is False
        assert data_untrusted["remote_url"] is None
        assert data_untrusted["refused_from"] is not None
        assert data_untrusted["refusal_notice"] is not None

        # 2. Trust directory
        client.post(
            "/api/v1/security/directory-trust-remote-memory/trust",
            json={"directory": tmpdir, "action": "trust"},
        )

        # 3. Resolve again -> authorized
        resp_trusted = client.post(
            "/api/v1/security/directory-trust-remote-memory/resolve",
            json=resolve_payload,
        )
        assert resp_trusted.status_code == 200
        data_trusted = resp_trusted.json()
        assert data_trusted["is_trusted"] is True
        assert data_trusted["is_outbound_authorized"] is True
        assert (
            data_trusted["remote_url"] == "https://enterprise.plur.internal/v1"
        )
        assert data_trusted["remote_token"] == "bearer-corp-secret-999"
        assert data_trusted["remote_scopes"] == ["group:security"]
        assert data_trusted["refusal_notice"] is None
