"""
[POS] tests/api/memory/test_memory_privacy_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.privacy_router
[OUTPUT] test_check_memory_privacy_clean_api, test_check_memory_privacy_secret_detected_api, test_sanitize_memory_content_api, test_enforce_memory_privacy_veto_api, test_get_privacy_config_api
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.privacy_gate import (
    MemoryPrivacyBoundaryGate,
    MemoryPrivacyConfig,
)
from starlette.testclient import TestClient

from app.api.memory.privacy_router import router as memory_privacy_router
from app.services.memory.memory_privacy_service import (
    MemoryPrivacyService,
    get_memory_privacy_service,
)


@pytest.fixture
def privacy_client() -> Generator[TestClient, None, None]:
    """Provide isolated TestClient mounting memory privacy router."""
    config = MemoryPrivacyConfig(block_on_critical=True, strict_mode=False)
    gate = MemoryPrivacyBoundaryGate(config=config)
    service = MemoryPrivacyService(gate=gate)

    test_app = FastAPI()
    test_app.include_router(memory_privacy_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_privacy_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_check_memory_privacy_clean_api(privacy_client: TestClient) -> None:
    """Verify clean operational notes pass inspection without modification."""
    clean_text = "Refactored user authentication to leverage standard Argon2 hashing."
    resp = privacy_client.post(
        "/api/memory/privacy/check",
        json={"content": clean_text, "source_path": "src/auth/service.py"},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["passed"] is True
    assert data["sensitivity_level"] == "public"
    assert len(data["findings"]) == 0
    assert data["redacted_content"] == clean_text
    assert data["violation_reason"] is None


def test_check_memory_privacy_secret_detected_api(privacy_client: TestClient) -> None:
    """Verify secrets are detected, classified as critical, and masked."""
    leak_text = (
        "Found credentials:\n"
        "sk-ant-api03-abcdef1234567890abcdef1234567890-XYZ12\n"
        "postgres://readonly:dbpassword123@prod-db.internal:5432/main"
    )
    resp = privacy_client.post(
        "/api/memory/privacy/check",
        json={"content": leak_text},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["passed"] is False
    assert data["sensitivity_level"] == "critical_secret"
    assert len(data["findings"]) >= 2
    types = {f["violation_type"] for f in data["findings"]}
    assert "api_key" in types
    assert "connection_uri" in types
    assert "[REDACTED:API_KEY]" in data["redacted_content"]
    assert "[REDACTED:CONNECTION_URI]" in data["redacted_content"]
    assert "dbpassword123" not in data["redacted_content"]


def test_sanitize_memory_content_api(privacy_client: TestClient) -> None:
    """Verify sanitize endpoint returns scrubbed text without raising error."""
    text_with_token = "Personal GitHub token: ghp_123456789012345678901234567890123456 used in CI"
    resp = privacy_client.post(
        "/api/memory/privacy/sanitize",
        json={"content": text_with_token},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["was_modified"] is True
    assert "ghp_" not in data["sanitized_content"]
    assert "[REDACTED:API_KEY]" in data["sanitized_content"]


def test_enforce_memory_privacy_veto_api(privacy_client: TestClient) -> None:
    """Verify enforce endpoint raises 403 Forbidden on critical secret leakage."""
    leak_text = "SSH key block:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
    resp = privacy_client.post(
        "/api/memory/privacy/enforce",
        json={"content": leak_text},
    )
    assert resp.status_code == 403
    error_detail = resp.json()["detail"]
    assert "Critical secret detected" in error_detail


def test_get_privacy_config_api(privacy_client: TestClient) -> None:
    """Verify config endpoint returns active memory privacy gate parameters."""
    resp = privacy_client.get("/api/memory/privacy/config")
    assert resp.status_code == 200
    cfg = resp.json()

    assert cfg["block_on_critical"] is True
    assert cfg["strict_mode"] is False
    assert isinstance(cfg["exclude_patterns"], list)
    assert any(".env" in p for p in cfg["exclude_patterns"])
