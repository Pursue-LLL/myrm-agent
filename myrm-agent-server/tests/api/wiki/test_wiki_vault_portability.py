"""Tests for wiki vault reveal/open/export portability endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID


@dataclass(frozen=True, slots=True)
class _FakeIdentity:
    user_id: str = LOCAL_USER_ID
    auth_source: str = "loopback"
    loopback: bool = True
    client_ip: str = "127.0.0.1"
    private_net: bool = False


@pytest.fixture(autouse=True)
def _bypass_auth():
    with patch(
        "app.middleware.auth.resolve_identity",
        return_value=_FakeIdentity(),
    ):
        yield


@pytest.fixture
def client():
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    return TestClient(app)


def test_vault_reveal_forbidden_outside_local_mode(client: TestClient) -> None:
    with patch("app.config.deploy_mode.is_local_mode", return_value=False):
        response = client.post("/api/v1/wiki/vault/reveal")
    assert response.status_code == 403


def test_vault_open_obsidian_forbidden_outside_local_mode(client: TestClient) -> None:
    with patch("app.config.deploy_mode.is_local_mode", return_value=False):
        response = client.post("/api/v1/wiki/vault/open-obsidian")
    assert response.status_code == 403
