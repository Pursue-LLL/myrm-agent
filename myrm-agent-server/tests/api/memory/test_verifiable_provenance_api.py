"""
[INPUT]: FastAPI TestClient, verifiable provenance payloads for token, proof, purge, and PII inspection
[OUTPUT]: Asserts verifying /provenance/token, /residency-proof, /purge, and /inspect-pii endpoints
[POS]: myrm-agent-server/tests/api/memory/test_verifiable_provenance_api.py
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.memory.verifiable_provenance_router import (
    get_provenance_service,
)
from app.api.memory.verifiable_provenance_router import (
    router as verifiable_provenance_router,
)

app = FastAPI()
app.include_router(verifiable_provenance_router)
client = TestClient(app)


def test_token_generation_api() -> None:
    payload = {
        "tenant_id": "tenant-test-01",
        "sandbox_id": "sb-test-01",
        "volume_id": "vol-test-01",
    }
    resp = client.post("/provenance/token", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["tenant_id"] == "tenant-test-01"
    assert data["sandbox_id"] == "sb-test-01"
    assert data["volume_id"] == "vol-test-01"
    assert len(data["environment_token"]) == 64


def test_residency_proof_api_success() -> None:
    service = get_provenance_service()
    volume_root = service.manager.prover._volume_root
    test_file = volume_root / "memory_residency_test.db"
    test_file.write_text("verifiable-isolated-data-content")

    token_resp = client.post(
        "/provenance/token",
        json={"tenant_id": "tenant-02", "sandbox_id": "sb-02", "volume_id": "vol-02"},
    )
    token = token_resp.json()["environment_token"]

    proof_payload = {
        "file_path": str(test_file),
        "context": {
            "tenant_id": "tenant-02",
            "sandbox_id": "sb-02",
            "volume_id": "vol-02",
            "environment_token": token,
        },
        "extra_metadata": {"cloud_region": "us-west-2"},
    }
    resp = client.post("/provenance/residency-proof", json=proof_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tenant_id"] == "tenant-02"
    assert data["storage_path"] == str(test_file)
    assert data["is_exclusive_volume"] is True
    assert data["file_inode"] > 0
    assert len(data["content_sha256"]) == 64
    assert data["metadata"]["cloud_region"] == "us-west-2"


def test_residency_proof_fail_closed_security() -> None:
    service = get_provenance_service()
    volume_root = service.manager.prover._volume_root
    test_file = volume_root / "isolated_memory.db"
    test_file.write_text("protected-memory")

    # Tampered token
    tampered_payload = {
        "file_path": str(test_file),
        "context": {
            "tenant_id": "tenant-evil",
            "sandbox_id": "sb-evil",
            "volume_id": "vol-evil",
            "environment_token": "tampered-bad-token",
        },
    }
    resp = client.post("/provenance/residency-proof", json=tampered_payload)
    assert resp.status_code == 403
    assert "Fail-Closed security rejection" in resp.json()["detail"]


def test_physical_purge_api() -> None:
    service = get_provenance_service()
    volume_root = service.manager.prover._volume_root
    purge_file = volume_root / "temp_to_purge.db"
    purge_file.write_text("data-requiring-gdpr-destruction-123456789")

    token_resp = client.post(
        "/provenance/token",
        json={"tenant_id": "tenant-03", "sandbox_id": "sb-03", "volume_id": "vol-03"},
    )
    token = token_resp.json()["environment_token"]

    purge_payload = {
        "file_path": str(purge_file),
        "context": {
            "tenant_id": "tenant-03",
            "sandbox_id": "sb-03",
            "volume_id": "vol-03",
            "environment_token": token,
        },
    }
    resp = client.post("/provenance/purge", json=purge_payload)
    assert resp.status_code == 200
    receipt = resp.json()
    assert receipt["tenant_id"] == "tenant-03"
    assert receipt["status"] == "verified_destroyed"
    assert receipt["bytes_overwritten"] > 0
    assert receipt["overwrite_passes"] == 3
    assert not purge_file.exists()


def test_inspect_pii_api() -> None:
    raw_text = (
        "User personal record: My child's name is Charlie Brown. "
        "Street: 101 Dalmatian Way, City: Metropolis. "
        "Credit card: 4111-2222-3333-4444."
    )
    resp = client.post("/provenance/inspect-pii", json={"text": raw_text})
    assert resp.status_code == 200
    data = resp.json()
    assert data["intercepted"] is True
    assert data["has_child_privacy_violation"] is True
    assert "child_identity" in data["detected_categories"]
    assert "precise_residential_address" in data["detected_categories"]
    assert "financial_instrument" in data["detected_categories"]
    assert "[REDACTED_CHILD_IDENTITY]" in data["sanitized_text"]
    assert "[REDACTED_RESIDENTIAL_ADDRESS]" in data["sanitized_text"]
    assert "[REDACTED_FINANCIAL_INSTRUMENT]" in data["sanitized_text"]
    assert "Charlie Brown" not in data["sanitized_text"]
