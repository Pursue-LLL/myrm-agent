"""Tests for OAuth token refresh credential resolution."""

from __future__ import annotations

from unittest.mock import patch

from pydantic import SecretStr

from app.services.agent.oauth_refresher import (
    GOOGLE_WORKSPACE_ISSUER,
    _resolve_oauth_client_credentials,
)


def test_google_workspace_uses_server_settings_not_blob() -> None:
    with (
        patch("app.config.settings.settings.google_client_id", "server-client-id"),
        patch(
            "app.config.settings.settings.google_client_secret",
            SecretStr("server-client-secret"),
        ),
    ):
        client_id, client_secret = _resolve_oauth_client_credentials(
            GOOGLE_WORKSPACE_ISSUER,
            {"client_id": "blob-id", "client_secret": "blob-secret"},
        )
    assert client_id == "server-client-id"
    assert client_secret == "server-client-secret"


def test_mcp_issuer_uses_blob_credentials() -> None:
    client_id, client_secret = _resolve_oauth_client_credentials(
        "custom_mcp",
        {"client_id": "blob-id", "client_secret": "blob-secret"},
    )
    assert client_id == "blob-id"
    assert client_secret == "blob-secret"
