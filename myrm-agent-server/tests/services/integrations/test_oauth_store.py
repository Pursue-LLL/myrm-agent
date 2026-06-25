"""Tests for oauth_store integration helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import is_oauth_issuer_connected


@pytest.mark.asyncio
async def test_is_oauth_issuer_connected_false_when_no_row() -> None:
    db = AsyncMock()
    with patch(
        "app.services.integrations.oauth_store.load_oauth_credentials_row",
        AsyncMock(return_value=None),
    ):
        assert await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER) is False


@pytest.mark.asyncio
async def test_is_oauth_issuer_connected_false_when_no_token() -> None:
    db = AsyncMock()
    row = MagicMock()
    row.config_value = {GOOGLE_WORKSPACE_ISSUER: {"refresh_token": "x"}}
    row.is_encrypted = False
    with patch(
        "app.services.integrations.oauth_store.load_oauth_credentials_row",
        AsyncMock(return_value=row),
    ):
        assert await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER) is False


@pytest.mark.asyncio
async def test_is_oauth_issuer_connected_true_when_token_present() -> None:
    db = AsyncMock()
    row = MagicMock()
    row.config_value = {GOOGLE_WORKSPACE_ISSUER: {"token": "access-token"}}
    row.is_encrypted = False
    with patch(
        "app.services.integrations.oauth_store.load_oauth_credentials_row",
        AsyncMock(return_value=row),
    ):
        assert await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER) is True
