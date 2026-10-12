"""Integration tests for Marketplace Manifest Source Pinning & Capability Contract API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.marketplace_contract_router import (
    router as marketplace_contract_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting marketplace_contract_router."""
    test_app = FastAPI(title="Marketplace Contract Test App")
    test_app.include_router(marketplace_contract_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_validate_manifest_endpoint(client: TestClient) -> None:
    payload = {
        "manifest": {
            "package_id": "hermes-live-voice",
            "name": "Live Voice Extension",
            "version": "0.5.0",
            "repo_url": "https://github.com/hermes/live-voice",
            "source_sha": "a1b2c3d4e5f60718293a4b5c6d7e8f901a2b3c4d",
            "tier": "OFFICIAL",
            "requires_host": ">=0.20.0",
            "platforms": ["macos", "linux"],
            "capabilities": {
                "provides_tools": ["voice_start", "voice_stop"],
                "provides_hooks": [],
                "provides_middleware": [],
                "requires_env": ["VOICE_API_KEY"],
                "declared_mcp_servers": [],
            },
            "publisher": "hermes-ai",
        },
        "target_platform": "macos",
    }
    resp = client.post("/api/v1/security/marketplace-contract/validate", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_valid"] is True
    assert data["platform_supported"] is True


def test_policy_crud_and_admission_endpoint(client: TestClient) -> None:
    # 1. Read default policy
    get_resp = client.get("/api/v1/security/marketplace-contract/policy")
    assert get_resp.status_code == 200
    assert get_resp.json()["enforce_strict_pinning"] is True

    # 2. Update policy to disallow COMMUNITY packages
    put_payload = {
        "policy": {
            "allowed_sources": [],
            "allowed_tiers": ["OFFICIAL", "VERIFIED"],
            "disallowed_capabilities": ["unauthorized_daemon"],
            "enforce_strict_pinning": True,
        }
    }
    put_resp = client.put("/api/v1/security/marketplace-contract/policy", json=put_payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["allowed_tiers"] == ["OFFICIAL", "VERIFIED"]

    # 3. Evaluate community manifest -> should be denied
    comm_manifest = {
        "manifest": {
            "package_id": "random-community-plugin",
            "name": "Community Mod",
            "version": "0.1.0",
            "repo_url": "https://github.com/random/plugin",
            "source_sha": "1234567890123456789012345678901234567890",
            "tier": "COMMUNITY",
            "requires_host": ">=0.1.0",
            "platforms": ["all"],
            "capabilities": {
                "provides_tools": [],
                "provides_hooks": [],
                "provides_middleware": [],
                "requires_env": [],
                "declared_mcp_servers": [],
            },
            "publisher": "random_user",
        }
    }
    eval_resp = client.post("/api/v1/security/marketplace-contract/evaluate", json=comm_manifest)
    assert eval_resp.status_code == 200
    eval_data = eval_resp.json()
    assert eval_data["is_admitted"] is False
    assert any("COMMUNITY" in v for v in eval_data["verdict"]["violations"])
