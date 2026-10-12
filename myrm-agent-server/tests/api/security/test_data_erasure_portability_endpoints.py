"""API endpoint tests for Verifiable Cryptographic Erasure and Complete Data Portability."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.data_erasure_portability_router import (
    router as data_erasure_portability_router,
)
from app.services.security.data_erasure_portability_service import (
    DataErasurePortabilityService,
    get_data_erasure_portability_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = DataErasurePortabilityService()
    app = FastAPI()
    app.include_router(data_erasure_portability_router)
    app.dependency_overrides[get_data_erasure_portability_service] = lambda: test_service
    return TestClient(app)


def test_register_key_and_purge_endpoints(client: TestClient, tmp_path: Path) -> None:
    # 1. Register DEK
    reg_resp = client.post(
        "/data-erasure/keys/register",
        json={"tenant_id": "tenant-compliance-test"},
    )
    assert reg_resp.status_code == 200
    reg_data = reg_resp.json()
    assert reg_data["tenant_id"] == "tenant-compliance-test"
    assert len(reg_data["key_fingerprint"]) == 64

    # 2. Setup a file to shred
    file_to_shred = tmp_path / "vectors.db"
    file_to_shred.write_bytes(b"EMBEDDINGS_DATA" * 40)
    assert file_to_shred.exists()

    # 3. Purge tenant data
    purge_resp = client.post(
        "/data-erasure/purge",
        json={
            "tenant_id": "tenant-compliance-test",
            "target_resource_types": ["VECTORS", "MEMORY"],
            "physical_path_to_shred": str(file_to_shred),
            "signer_identity": "test-ca",
        },
    )
    assert purge_resp.status_code == 200
    purge_data = purge_resp.json()
    assert purge_data["success"] is True
    assert purge_data["certificate"] is not None
    assert purge_data["shredded_files_count"] == 1
    assert not file_to_shred.exists()

    # 4. Verify certificate endpoint
    cert = purge_data["certificate"]
    v_resp = client.post(
        "/data-erasure/certificates/verify",
        json={"certificate": cert},
    )
    assert v_resp.status_code == 200
    assert v_resp.json()["is_valid"] is True


def test_export_and_verify_bundle_endpoints(client: TestClient) -> None:
    # 1. Export GDPR Article 20 bundle
    exp_resp = client.post(
        "/data-erasure/export",
        json={
            "tenant_id": "tenant-gdpr-101",
            "conversations": [{"session_id": "conv-1", "title": "API Design"}],
            "memory_entries": [{"id": "mem-1", "content": "Prefers FastAPI"}],
            "agent_configs": [{"agent_name": "architect", "model": "claude-3"}],
        },
    )
    assert exp_resp.status_code == 200
    bundle = exp_resp.json()
    assert bundle["tenant_id"] == "tenant-gdpr-101"
    assert len(bundle["bundle_sha256"]) == 64

    # 2. Verify authentic bundle
    v_resp = client.post(
        "/data-erasure/export/verify",
        json={"bundle": bundle},
    )
    assert v_resp.status_code == 200
    assert v_resp.json()["is_valid"] is True


def test_shred_path_endpoint(client: TestClient, tmp_path: Path) -> None:
    test_f = tmp_path / "to_delete.txt"
    test_f.write_text("senseless data")
    assert test_f.exists()

    resp = client.post(
        "/data-erasure/shred-path",
        json={"path": str(test_f), "passes": 3},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["files_shredded"] == 1
    assert not test_f.exists()
