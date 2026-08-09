"""Tests for MCP OAuth token store concurrency.

An in-flight token refresh must not resurrect a server that was disconnected
while its refresh HTTP request was still running.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.mcp.oauth import (
    MCPOAuthConfig,
    MCPOAuthToken,
)
from sqlalchemy import delete, select

from app.database.connection import get_session
from app.database.models import UserConfig
from app.services.config.encryption import get_encryption_service

CONFIG_KEY = "mcpOAuthTokens"
SERVER_NAME = "notion-test"


def _oauth_config() -> MCPOAuthConfig:
    return MCPOAuthConfig(
        authorization_endpoint="",
        token_endpoint="https://api.example.com/oauth/token",
        client_id="client-id",
        client_secret="client-secret",
    )


def _expired_token() -> MCPOAuthToken:
    return MCPOAuthToken(
        access_token="old-token",
        token_type="Bearer",
        refresh_token="refresh-token",
        expires_at=time.time() - 100,
        scope="read",
    )


@pytest.fixture
async def seeded_token():
    from app.services.agent.backends.mcp_oauth_store import (
        DatabaseMCPOAuthTokenStore,
    )

    store = DatabaseMCPOAuthTokenStore()
    async with get_session() as db:
        await db.execute(delete(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
        await db.commit()

    await store.save_token_with_config(SERVER_NAME, _expired_token(), _oauth_config())

    yield store

    async with get_session() as db:
        await db.execute(delete(UserConfig).where(UserConfig.config_key == CONFIG_KEY))
        await db.commit()


def _decrypt_blob(row: UserConfig) -> dict[str, object]:
    service = get_encryption_service()
    val = row.config_value
    if row.is_encrypted:
        if isinstance(val, str):
            val = service.decrypt(val)
        elif isinstance(val, dict) and "_cipher" in val:
            val = service.decrypt(val["_cipher"])
    return val if isinstance(val, dict) else {}


@pytest.mark.asyncio
async def test_refresh_discards_when_server_disconnected(seeded_token) -> None:
    """A disconnect during an in-flight MCP refresh must not resurrect the server."""
    store = seeded_token
    config = _oauth_config()

    async def _post(*args, **kwargs):
        await asyncio.sleep(0.05)
        # User disconnects the server while the refresh HTTP request is in flight.
        await store.delete_token(SERVER_NAME)
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "fresh-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=_post):
        result = await store.refresh_token_exchange(
            SERVER_NAME, config, "refresh-token"
        )

    assert result is None
    async with get_session() as db:
        row = (
            (
                await db.execute(
                    select(UserConfig).where(UserConfig.config_key == CONFIG_KEY)
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        assert SERVER_NAME not in _decrypt_blob(row)


@pytest.mark.asyncio
async def test_refresh_persists_when_server_connected(seeded_token) -> None:
    """Normal refresh (no concurrent disconnect) still persists the new token."""
    store = seeded_token
    config = _oauth_config()

    async def _post(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "fresh-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=_post):
        result = await store.refresh_token_exchange(
            SERVER_NAME, config, "refresh-token"
        )

    assert result is not None
    assert result.access_token == "fresh-token"
    async with get_session() as db:
        row = (
            (
                await db.execute(
                    select(UserConfig).where(UserConfig.config_key == CONFIG_KEY)
                )
            )
            .scalars()
            .first()
        )
        assert row is not None
        blob = _decrypt_blob(row)
        assert SERVER_NAME in blob
        assert blob[SERVER_NAME]["access_token"] == "fresh-token"
