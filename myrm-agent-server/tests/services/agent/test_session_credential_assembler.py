"""Tests for SessionCredentialAssembler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import EphemeralUserCredential

from app.services.agent.session_credential_assembler import (
    XAI_ISSUER,
    assemble_session_credentials,
)


@pytest.mark.asyncio
async def test_assemble_oauth_and_xai_provider_credentials() -> None:
    oauth_dict = {
        "google_workspace": {
            "token": "oauth-token",
            "scope": "email",
            "user_id": "u1",
        }
    }
    providers_dict = {
        "providers": [
            {"id": "xai-main", "apiKey": "xai-key", "apiUrl": "https://api.x.ai/v1"},
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

    issuers = {cred.issuer for cred in credentials}
    assert "google_workspace" in issuers
    assert XAI_ISSUER in issuers

    xai_cred = next(c for c in credentials if c.issuer == XAI_ISSUER)
    assert xai_cred.token == "xai-key"
    assert xai_cred.scope == "https://api.x.ai/v1"


@pytest.mark.asyncio
async def test_assemble_merges_channel_token_with_oauth() -> None:
    oauth_dict = {"google_workspace": {"token": "oauth-token"}}

    mock_store = MagicMock()
    mock_store.get = AsyncMock(
        return_value={"user_access_token": "channel-token", "user_id": "peer-1"},
    )

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ), patch("app.channels.storage.CredentialsStore", return_value=mock_store):
        credentials = await assemble_session_credentials(
            oauth_credentials_dict=oauth_dict,
            channel="feishu",
        )

    issuers = {cred.issuer for cred in credentials}
    assert "google_workspace" in issuers
    assert "feishu" in issuers


@pytest.mark.asyncio
async def test_assemble_returns_empty_on_total_failure() -> None:
    with patch(
        "app.services.agent.session_credential_assembler._oauth_credentials_from_dict",
        side_effect=RuntimeError("boom"),
    ):
        credentials = await assemble_session_credentials(oauth_credentials_dict={"x": {"token": "t"}})

    assert credentials == ()


def test_xai_issuer_constant() -> None:
    assert XAI_ISSUER == "xai"
