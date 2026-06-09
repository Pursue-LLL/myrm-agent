"""Tests for GET /api/v1/health/info capability detection."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="health")
@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_system_info_returns_capabilities_booleans(client: TestClient) -> None:
    response = client.get("/api/v1/health/info")
    assert response.status_code == 200

    body = response.json()
    assert "deploy_mode" in body
    assert "database" in body
    assert "qdrant" in body
    assert "embedding" in body
    assert "reranker" in body

    # Assert newly added capability check indicators are returned and typed correctly
    assert "local_stt_available" in body
    assert isinstance(body["local_stt_available"], bool)
