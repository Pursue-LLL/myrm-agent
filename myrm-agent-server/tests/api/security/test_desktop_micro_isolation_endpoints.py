"""Integration tests for Desktop Host Auth & Tool Routing Micro-Isolation API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.desktop_micro_isolation_router import (
    router as desktop_micro_isolation_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting desktop_micro_isolation_router."""
    test_app = FastAPI(title="Desktop Micro-Isolation Test App")
    test_app.include_router(desktop_micro_isolation_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_sanitize_env_endpoint(client: TestClient) -> None:
    payload = {
        "host_env": {
            "OPENAI_API_KEY": "sk-secret-sample",
            "HOME": "/Users/developer",
            "DATABASE_URL": "postgresql://root@db:5432/app",
        }
    }
    resp = client.post("/api/v1/security/desktop-micro-isolation/sanitize-env", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "OPENAI_API_KEY" not in data["clean_env"]
    assert "DATABASE_URL" not in data["clean_env"]
    assert data["clean_env"]["HOME"] == "/Users/developer"
    assert "OPENAI_API_KEY" in data["stripped_keys"]


def test_route_tool_endpoint_micro_sandbox(client: TestClient) -> None:
    payload = {
        "tool_name": "bash",
        "arguments": {"command": "echo 'safe test'"},
        "host_env": {"ANTHROPIC_API_KEY": "sk-ant-test"},
    }
    resp = client.post("/api/v1/security/desktop-micro-isolation/route-tool", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["tool_name"] == "bash"
    assert data["destination"] == "MICRO_ISOLATION_SANDBOX"
    assert data["isolation_level"] == "MICRO_SANDBOX"
    assert "ANTHROPIC_API_KEY" in data["stripped_credential_keys"]
    assert not data["is_blocked"]


def test_route_tool_endpoint_forbidden_path(client: TestClient) -> None:
    payload = {
        "tool_name": "file_write",
        "arguments": {"path": "/etc/shadow", "content": "hack"},
        "target_path": "/etc/shadow",
    }
    resp = client.post("/api/v1/security/desktop-micro-isolation/route-tool", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_blocked"] is True
    assert "forbidden system path" in data["error_message"]


def test_isolation_status_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/security/desktop-micro-isolation/isolation-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "provider_available" in data
    assert "default_isolation_level" in data
    assert data["fail_closed_enforced"] is True
    assert "disclosure_notice" in data
