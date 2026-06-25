"""Tests for session_credentials_scope context manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import user_credentials_ctx

from app.services.agent.session_credential_assembler import session_credentials_scope


@pytest.mark.asyncio
async def test_session_credentials_scope_injects_and_resets() -> None:
    oauth_dict = {"google_workspace": {"token": "oauth-token"}}

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ):
        async with session_credentials_scope(oauth_credentials_dict=oauth_dict):
            active = user_credentials_ctx.get()
            assert any(c.issuer == "google_workspace" for c in active)

    assert user_credentials_ctx.get() == ()


@pytest.mark.asyncio
async def test_session_credentials_scope_channel_oauth_merge() -> None:
    """Channel + OAuth merge — regression guard for executor credential assembly."""
    oauth_dict = {"google_workspace": {"token": "oauth-token"}}

    mock_store = MagicMock()
    mock_store.get = AsyncMock(
        return_value={"user_access_token": "feishu-token", "user_id": "u1"},
    )

    with patch(
        "app.services.agent.oauth_refresher.refresh_oauth_token",
        new_callable=AsyncMock,
    ), patch("app.channels.storage.CredentialsStore", return_value=mock_store):
        async with session_credentials_scope(oauth_credentials_dict=oauth_dict, channel="feishu"):
            active = user_credentials_ctx.get()
            issuers = {c.issuer for c in active}
            assert "google_workspace" in issuers
            assert "feishu" in issuers

    assert user_credentials_ctx.get() == ()
