"""API endpoint tests for Scoped Folder Permission Dialog and Sandbox Dynamic Mount Suite."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.scoped_folder_sandbox_mount_router import (
    router as scoped_folder_sandbox_mount_router,
)
from app.services.security.scoped_folder_sandbox_mount_service import (
    ScopedFolderSandboxMountService,
    get_scoped_folder_mount_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ScopedFolderSandboxMountService()
    app = FastAPI()
    app.include_router(scoped_folder_sandbox_mount_router)
    app.dependency_overrides[get_scoped_folder_mount_service] = lambda: test_service
    return TestClient(app)


def test_validate_path_endpoint(client: TestClient) -> None:
    # 1. Prohibited sensitive system path
    resp_bad = client.post(
        "/scoped-folder-mount/validate-path",
        json={"path": "/etc"},
    )
    assert resp_bad.status_code == 200
    assert resp_bad.json()["is_blocked"] is True
    assert "SYSTEM_PREFIX" in resp_bad.json()["matched_rule"]

    # 2. Benign path
    resp_good = client.post(
        "/scoped-folder-mount/validate-path",
        json={"path": "/tmp"},
    )
    assert resp_good.status_code == 200
    assert resp_good.json()["is_blocked"] is False


def test_grant_request_and_mount_spec_endpoints(
    client: TestClient,
    tmp_path: Path,
) -> None:
    valid_folder = tmp_path / "ClientContracts"
    valid_folder.mkdir()

    # 1. Successful grant request
    resp_grant = client.post(
        "/scoped-folder-mount/grants/request",
        json={
            "folder_path": str(valid_folder),
            "access_mode": "READ_ONLY",
            "lifecycle": "EPHEMERAL_PER_SESSION",
            "lease_seconds": 3600.0,
            "alias_slug": "contracts",
        },
    )
    assert resp_grant.status_code == 201
    grant_data = resp_grant.json()
    grant_id = grant_data["grant_id"]
    assert grant_id.startswith("grant-")
    assert grant_data["sandbox_mount_path"] == "/workspace/granted/contracts"

    # 2. Query mount spec
    resp_spec = client.get(f"/scoped-folder-mount/grants/{grant_id}/mount-spec")
    assert resp_spec.status_code == 200
    spec_data = resp_spec.json()
    assert spec_data["read_only"] is True
    assert spec_data["sandbox_target_path"] == "/workspace/granted/contracts"

    # 3. List grants
    resp_list = client.get("/scoped-folder-mount/grants?active_only=true")
    assert resp_list.status_code == 200
    assert any(g["grant_id"] == grant_id for g in resp_list.json())

    # 4. Revoke grant
    resp_revoke = client.post(f"/scoped-folder-mount/grants/{grant_id}/revoke")
    assert resp_revoke.status_code == 200
    assert resp_revoke.json()["revoked"] is True

    # 5. Non-existent grant spec
    resp_spec_after = client.get(f"/scoped-folder-mount/grants/{grant_id}/mount-spec")
    assert resp_spec_after.status_code == 404


def test_grant_request_forbidden_on_blacklist(client: TestClient) -> None:
    resp = client.post(
        "/scoped-folder-mount/grants/request",
        json={
            "folder_path": "/etc",
            "access_mode": "READ_ONLY",
        },
    )
    assert resp.status_code == 403
    assert "blocked by security policy" in resp.json()["detail"]
