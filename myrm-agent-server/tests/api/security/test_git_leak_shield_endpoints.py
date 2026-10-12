"""Integration tests for Git Leak Shield API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.git_leak_shield_router import router as git_leak_shield_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting git_leak_shield_router."""
    test_app = FastAPI(title="Git Leak Shield Test App")
    test_app.include_router(git_leak_shield_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_scan_diff_endpoint(client: TestClient) -> None:
    # 1. Leaked diff
    payload = {
        "diff_content": "+GITHUB_KEY = 'ghp_abcdef123456789012345678901234567890'\n",
        "file_path": "auth.ts",
    }
    resp = client.post("/api/v1/security/git-shield/scan-diff", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["has_leak"] is True
    assert len(data["findings"]) == 1
    assert data["findings"][0]["secret_type"] == "GitHub Access Token"
    assert "****" in data["findings"][0]["masked_snippet"]

    # 2. Clean diff
    clean_payload = {
        "diff_content": "+console.log('clean build');\n",
        "file_path": "main.ts",
    }
    clean_resp = client.post("/api/v1/security/git-shield/scan-diff", json=clean_payload)
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()
    assert clean_data["has_leak"] is False
    assert len(clean_data["findings"]) == 0


def test_check_commit_endpoint(client: TestClient) -> None:
    # 1. Blocked commit
    block_payload = {
        "command": "git commit -m 'leaking credentials'",
        "diff_content": "+KEY = 'AKIAIOSFODNN7EXAMPLE'\n",
    }
    block_resp = client.post("/api/v1/security/git-shield/check-commit", json=block_payload)
    assert block_resp.status_code == 200
    block_data = block_resp.json()
    assert block_data["blocked"] is True
    assert len(block_data["findings"]) == 1

    # 2. Permitted clean commit
    clean_payload = {
        "command": "git commit -m 'clean work'",
        "diff_content": "+let count = 0;\n",
    }
    clean_resp = client.post("/api/v1/security/git-shield/check-commit", json=clean_payload)
    assert clean_resp.status_code == 200
    clean_data = clean_resp.json()
    assert clean_data["blocked"] is False
    assert len(clean_data["findings"]) == 0


def test_redact_egress_endpoint(client: TestClient) -> None:
    payload = {
        "text": "Execution log: AWS key AKIAIOSFODNN7EXAMPLE was initialized.",
    }
    resp = client.post("/api/v1/security/git-shield/redact", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["redactions_count"] == 1
    assert "AWS Access Key ID" in data["detected_types"]
    assert "AKIAIOSFODNN7EXAMPLE" not in data["redacted_text"]
    assert "****" in data["redacted_text"]
