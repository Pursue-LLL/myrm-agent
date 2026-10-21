"""Tests for xAI OAuth priority over API Key in session credential assembly."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.session_credential_assembler import (
    XAI_ISSUER,
    assemble_session_credentials,
)


@pytest.mark.asyncio
async def test_xai_oauth_token_takes_priority_over_api_key() -> None:
    """When both xAI OAuth and API Key are available, only OAuth credential is used."""
    oauth_dict = {
        XAI_ISSUER: {
            "token": "oauth-supergrok-token",
            "scope": "openid profile",
            "user_id": "user-123",
            "expires_at": 9999999999,
        }
    }
    providers_dict = {
        "providers": [
            {"id": "xai-main", "apiKey": "xai-api-key", "apiUrl": "https://api.x.ai/v1"},
        ]
    }

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict=oauth_dict,
            providers_dict=providers_dict,
        )

    xai_creds = [c for c in credentials if c.issuer == XAI_ISSUER]
    assert len(xai_creds) == 1, "Only one xAI credential should exist"
    assert xai_creds[0].token == "oauth-supergrok-token"


@pytest.mark.asyncio
async def test_xai_api_key_used_when_no_oauth() -> None:
    """When only API Key is available (no xAI OAuth), API Key credential is used."""
    oauth_dict = {
        "google_workspace": {"token": "gw-token", "scope": "email"},
    }
    providers_dict = {
        "providers": [
            {"id": "xai-main", "apiKey": "xai-api-key", "apiUrl": "https://api.x.ai/v1"},
        ]
    }

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict=oauth_dict,
            providers_dict=providers_dict,
        )

    xai_creds = [c for c in credentials if c.issuer == XAI_ISSUER]
    assert len(xai_creds) == 1
    assert xai_creds[0].token == "xai-api-key"


@pytest.mark.asyncio
async def test_no_xai_credentials_when_neither_available() -> None:
    """When neither OAuth nor API Key is available, no xAI credential exists."""
    oauth_dict = {
        "google_workspace": {"token": "gw-token"},
    }
    providers_dict = {
        "providers": [
            {"id": "openai-main", "apiKey": "sk-xxx", "apiUrl": "https://api.openai.com/v1"},
        ]
    }

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict=oauth_dict,
            providers_dict=providers_dict,
        )

    xai_creds = [c for c in credentials if c.issuer == XAI_ISSUER]
    assert len(xai_creds) == 0
