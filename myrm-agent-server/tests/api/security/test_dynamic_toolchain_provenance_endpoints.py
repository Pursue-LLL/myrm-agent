"""
Integration tests for Dynamic Toolchain Supply Chain Provenance & Pre-Install Sandbox Hardening REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.dynamic_toolchain_provenance_router import (
    router as dynamic_toolchain_provenance_router,
)
from app.services.security.dynamic_toolchain_provenance_service import (
    DynamicToolchainProvenanceService,
    get_dynamic_toolchain_provenance_service,
)


def _generate_sig(publisher_id: str, sha256_hex: str) -> str:
    salt = b"myrm-provenance-anchor-salt"
    msg = f"{publisher_id}:{sha256_hex}".encode()
    return "sig_v1_" + hmac.new(salt, msg, hashlib.sha256).hexdigest()


@pytest.fixture
def client() -> TestClient:
    service = DynamicToolchainProvenanceService()
    app = FastAPI()
    app.include_router(dynamic_toolchain_provenance_router)
    app.dependency_overrides[get_dynamic_toolchain_provenance_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_and_install_approved(client: TestClient) -> None:
    code = "def multiply(x: int, y: int) -> int:\n    return x * y\n"
    sha = hashlib.sha256(code.encode()).hexdigest()
    sig = _generate_sig("myrm-official", sha)

    resp = client.post(
        "/dynamic-toolchain-provenance/evaluate-and-install",
        json={
            "source_code": code,
            "manifest": {
                "skill_id": "math-helper",
                "version": "1.0.0",
                "publisher_id": "myrm-official",
                "source_sha256": sha,
                "signature": sig,
                "declared_domains": ["api.math.org"],
                "declared_paths": ["/workspace/math"],
                "declared_env_keys": ["PRECISION"],
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_installation_approved"] is True
    assert data["is_provenance_valid"] is True
    assert data["is_ast_clean"] is True
    assert data["confinement_policy"]["skill_id"] == "math-helper"
    assert "/workspace/math" in data["confinement_policy"]["allowed_paths"]


def test_endpoint_evaluate_and_install_blocked(client: TestClient) -> None:
    code = "eval('import sys; sys.exit(1)')"
    sha = hashlib.sha256(code.encode()).hexdigest()
    sig = _generate_sig("myrm-official", sha)

    resp = client.post(
        "/dynamic-toolchain-provenance/evaluate-and-install",
        json={
            "source_code": code,
            "manifest": {
                "skill_id": "eval-tool",
                "version": "1.0.0",
                "publisher_id": "myrm-official",
                "source_sha256": sha,
                "signature": sig,
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_installation_approved"] is False
    assert data["is_ast_clean"] is False
    assert len(data["ast_findings"]) >= 1


def test_endpoint_verify_provenance_only(client: TestClient) -> None:
    code = "def ping(): pass\n"
    sha = hashlib.sha256(code.encode()).hexdigest()
    sig = _generate_sig("myrm-official", sha)

    resp = client.post(
        "/dynamic-toolchain-provenance/verify-provenance",
        json={
            "source_code": code,
            "manifest": {
                "skill_id": "pinger",
                "version": "0.1.0",
                "publisher_id": "myrm-official",
                "source_sha256": sha,
                "signature": sig,
            },
        },
    )
    assert resp.status_code == 200
    assert resp.json()["provenance_status"] == "VERIFIED"


def test_endpoint_scan_ast_only(client: TestClient) -> None:
    code = "import subprocess\nsubprocess.run(['ls'])\n"
    resp = client.post(
        "/dynamic-toolchain-provenance/scan-ast",
        json={"source_code": code, "skill_id": "subp-tool"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_clean"] is False
    assert len(data["findings"]) >= 1


def test_endpoint_manage_publishers(client: TestClient) -> None:
    reg_resp = client.post(
        "/dynamic-toolchain-provenance/publishers/register",
        json={"publisher_id": "trusted-partner"},
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json() is True

    rev_resp = client.post(
        "/dynamic-toolchain-provenance/publishers/revoke",
        json={"publisher_id": "trusted-partner"},
    )
    assert rev_resp.status_code == 200
    assert rev_resp.json() is True


def test_endpoint_check_permission(client: TestClient) -> None:
    resp = client.post(
        "/dynamic-toolchain-provenance/confinement/check-permission",
        json={
            "policy": {
                "policy_id": "conf-001",
                "skill_id": "scraper",
                "allowed_domains": ["example.com"],
                "allowed_paths": ["/workspace/downloads"],
                "allowed_env_keys": ["MAX_ITEMS"],
                "is_confined": True,
                "created_at": 12345.0,
            },
            "target_type": "network",
            "target_value": "example.com",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["permitted"] is True


def test_endpoint_metrics(client: TestClient) -> None:
    resp = client.get("/dynamic-toolchain-provenance/metrics")
    assert resp.status_code == 200
    metrics = resp.json()
    assert "provenance_checks_total" in metrics
    assert "installations_approved_total" in metrics
