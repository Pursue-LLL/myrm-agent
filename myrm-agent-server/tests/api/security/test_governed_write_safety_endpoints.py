"""
[POS] tests/api/security/test_governed_write_safety_endpoints.py
[INPUT] app.api.security.governed_write_safety_router, app.services.security.governed_write_safety_service
[OUTPUT] Integration tests for String-Is-Never-Authority Governed Write Safety REST endpoints
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.governed_write_safety_router import (
    router as governed_write_safety_router,
)
from app.services.security.governed_write_safety_service import (
    GovernedWriteSafetyService,
    get_governed_write_safety_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = GovernedWriteSafetyService()
    app = FastAPI()
    app.include_router(governed_write_safety_router)
    app.dependency_overrides[get_governed_write_safety_service] = lambda: service
    return TestClient(app)


def test_endpoint_register_and_resolve_lifecycle(client: TestClient) -> None:
    # 1. Register path behind opaque ID
    reg_resp = client.post(
        "/governed-write-safety/register",
        json={"raw_path": "/var/data/secure_config.yaml"},
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    opaque_id = reg_data["opaque_file_id"]
    assert opaque_id.startswith("@file_")
    assert reg_data["raw_path"] == "/var/data/secure_config.yaml"

    # 2. Resolve opaque ID
    resolve_resp = client.get(f"/governed-write-safety/resolve/{opaque_id}")
    assert resolve_resp.status_code == 200
    resolve_data = resolve_resp.json()
    assert resolve_data["raw_path"] == "/var/data/secure_config.yaml"
    assert resolve_data["opaque_file_id"] == opaque_id

    # 3. Resolve non-existent ID -> 404
    not_found_resp = client.get("/governed-write-safety/resolve/@file_nonexistent")
    assert not_found_resp.status_code == 404


def test_endpoint_propose_approve_and_commit_success(client: TestClient) -> None:
    # 1. Register
    reg_resp = client.post(
        "/governed-write-safety/register",
        json={"raw_path": "/workspace/server.ts"},
    )
    opaque_id = reg_resp.json()["opaque_file_id"]

    # 2. Propose edit
    base_content = "const port = 3000;"
    candidate_content = "const port = 8080;"
    prop_resp = client.post(
        "/governed-write-safety/propose",
        json={
            "opaque_file_id": opaque_id,
            "current_disk_content": base_content,
            "candidate_content": candidate_content,
        },
    )
    assert prop_resp.status_code == 200
    prop_data = prop_resp.json()
    prop_id = prop_data["proposal_id"]
    assert prop_data["status"] == "proposed"
    assert prop_data["opaque_file_id"] == opaque_id

    # 3. Approve edit
    appr_resp = client.post(
        "/governed-write-safety/approve",
        json={"proposal_id": prop_id},
    )
    assert appr_resp.status_code == 200
    lease_token = appr_resp.json()["lease_token"]
    assert lease_token.startswith("lease-tok-")

    # 4. Commit edit
    commit_resp = client.post(
        "/governed-write-safety/commit",
        json={
            "proposal_id": prop_id,
            "lease_token": lease_token,
            "current_disk_content": base_content,
        },
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.json()
    assert commit_data["success"] is True
    assert commit_data["status"] == "committed"
    assert commit_data["verified_disk_hash"] is not None
    snap_id = commit_data["pre_image_snapshot_id"]
    assert snap_id is not None

    # 5. Query proposal
    get_prop_resp = client.get(f"/governed-write-safety/proposal/{prop_id}")
    assert get_prop_resp.status_code == 200
    assert get_prop_resp.json()["status"] == "committed"

    # 6. Query snapshot
    get_snap_resp = client.get(f"/governed-write-safety/snapshot/{snap_id}")
    assert get_snap_resp.status_code == 200
    assert get_snap_resp.json()["content_preview"] == base_content


def test_endpoint_commit_stale_rejection(client: TestClient) -> None:
    # 1. Register
    reg_resp = client.post(
        "/governed-write-safety/register",
        json={"raw_path": "/workspace/critical.py"},
    )
    opaque_id = reg_resp.json()["opaque_file_id"]

    # 2. Propose edit
    base_content = "SECRET_KEY = 'old'"
    candidate_content = "SECRET_KEY = 'new'"
    prop_resp = client.post(
        "/governed-write-safety/propose",
        json={
            "opaque_file_id": opaque_id,
            "current_disk_content": base_content,
            "candidate_content": candidate_content,
        },
    )
    prop_id = prop_resp.json()["proposal_id"]

    # 3. Approve
    appr_resp = client.post(
        "/governed-write-safety/approve",
        json={"proposal_id": prop_id},
    )
    lease_token = appr_resp.json()["lease_token"]

    # 4. Commit with tampered disk content
    commit_resp = client.post(
        "/governed-write-safety/commit",
        json={
            "proposal_id": prop_id,
            "lease_token": lease_token,
            "current_disk_content": "SECRET_KEY = 'externally_mutated'",
        },
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.json()
    assert commit_data["success"] is False
    assert commit_data["status"] == "stale_rejected"
    assert commit_data["conflict_bundle"] is not None
    assert commit_data["conflict_bundle"]["opaque_file_id"] == opaque_id
    assert "Concurrent modification detected" in commit_data["conflict_bundle"]["reason"]
