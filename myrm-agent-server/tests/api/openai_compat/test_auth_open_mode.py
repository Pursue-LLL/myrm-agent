"""Tests for open authentication mode (proxySettings.auth.allow_any_key).

Verifies that when open auth is enabled, any non-empty Bearer token is
accepted, and when disabled, only valid DB keys work.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.openai_compat import auth as auth_module
from app.main import app


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


def _reset_auth_cache():
    auth_module._open_auth_cache = (0.0, False)


class TestOpenAuthMode:
    """Tests for dual-mode authentication."""

    @pytest.mark.asyncio
    async def test_open_auth_accepts_any_token(self, client: AsyncClient):
        """When open auth is enabled, any non-empty Bearer token should work."""
        _reset_auth_cache()
        with patch.object(
            auth_module,
            "_is_open_auth_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer hermes-proxy"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_open_auth_rejects_empty_token(self, client: AsyncClient):
        """Even in open auth, empty Bearer token should fail."""
        _reset_auth_cache()
        with patch.object(
            auth_module,
            "_is_open_auth_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer "},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_open_auth_rejects_missing_header(self, client: AsyncClient):
        """Even in open auth, missing Authorization header should fail."""
        _reset_auth_cache()
        with patch.object(
            auth_module,
            "_is_open_auth_enabled",
            new_callable=AsyncMock,
            return_value=True,
        ):
            resp = await client.get("/v1/models")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_strict_mode_rejects_arbitrary_token(self, client: AsyncClient):
        """When open auth is disabled, arbitrary tokens should fail."""
        _reset_auth_cache()
        with patch.object(
            auth_module,
            "_is_open_auth_enabled",
            new_callable=AsyncMock,
            return_value=False,
        ):
            resp = await client.get(
                "/v1/models",
                headers={"Authorization": "Bearer random-token-xyz"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_cache_respects_ttl(self):
        """_is_open_auth_enabled should use cached value within TTL."""
        import time

        auth_module._open_auth_cache = (time.monotonic(), True)
        result = await auth_module._is_open_auth_enabled()
        assert result is True

    @pytest.mark.asyncio
    async def test_cache_expires(self):
        """_is_open_auth_enabled should re-fetch after TTL expires."""
        import time

        auth_module._open_auth_cache = (
            time.monotonic() - auth_module._OPEN_AUTH_CACHE_TTL - 1,
            True,
        )
        result = await auth_module._is_open_auth_enabled()
        assert result is False
