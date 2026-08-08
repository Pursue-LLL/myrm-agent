"""GitHub webhook URL endpoint tests."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="channels_local")


@pytest.fixture
def client() -> TestClient:
    with TestClient(app, raise_server_exceptions=True) as test_client:
        yield test_client


def test_github_webhook_url_uses_public_ingress(client: TestClient) -> None:
    """Public Ingress configured → returns the public URL with public=True."""
    with patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        return_value="https://agent.example.com",
    ):
        response = client.get("/api/v1/channels/manage/github/webhook-url")

    assert response.status_code == 200
    data = response.json()
    assert data["webhookUrl"] == "https://agent.example.com/api/channels/github/webhook"
    assert data["public"] is True


def test_github_webhook_url_falls_back_to_request_base(client: TestClient) -> None:
    """No public Ingress → falls back to the request base URL with public=False."""
    with patch(
        "app.core.infra.ingress.get_public_ingress_base_url",
        return_value="",
    ):
        response = client.get("/api/v1/channels/manage/github/webhook-url")

    assert response.status_code == 200
    data = response.json()
    assert data["webhookUrl"].startswith("http://testserver/api/channels/github/webhook")
    assert data["public"] is False
