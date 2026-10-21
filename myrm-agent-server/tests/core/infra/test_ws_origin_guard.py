"""Tests for WebSocket Origin validation guard."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.infra.ws_origin_guard import _get_allowed_origins, verify_ws_origin


def _make_ws(origin: str | None = None) -> MagicMock:
    """Create a mock WebSocket with optional Origin header."""
    ws = AsyncMock()
    headers: dict[str, str] = {}
    if origin is not None:
        headers["origin"] = origin
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(side_effect=lambda key, default=None: headers.get(key, default))
    return ws


class TestVerifyWsOrigin:
    """Tests for verify_ws_origin function."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clear lru_cache between tests."""
        _get_allowed_origins.cache_clear()

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,http://localhost:3001,tauri://localhost"},
        ),
    )
    @pytest.mark.asyncio
    async def test_no_origin_header_allows(self, _mock_settings: object) -> None:
        """Non-browser clients (no Origin header) should be allowed."""
        ws = _make_ws(origin=None)
        result = await verify_ws_origin(ws)
        assert result is True
        ws.close.assert_not_called()

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,http://localhost:3001,tauri://localhost"},
        ),
    )
    @pytest.mark.asyncio
    async def test_allowed_origin_passes(self, _mock_settings: object) -> None:
        """Origin in the allowlist should be accepted."""
        ws = _make_ws(origin="http://localhost:3000")
        result = await verify_ws_origin(ws)
        assert result is True
        ws.close.assert_not_called()

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,http://localhost:3001,tauri://localhost"},
        ),
    )
    @pytest.mark.asyncio
    async def test_tauri_origin_passes(self, _mock_settings: object) -> None:
        """tauri://localhost should be accepted."""
        ws = _make_ws(origin="tauri://localhost")
        result = await verify_ws_origin(ws)
        assert result is True
        ws.close.assert_not_called()

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,http://localhost:3001,tauri://localhost"},
        ),
    )
    @pytest.mark.asyncio
    async def test_disallowed_origin_rejected(self, _mock_settings: object) -> None:
        """Origin NOT in the allowlist should be rejected with 4003."""
        ws = _make_ws(origin="http://evil.com")
        result = await verify_ws_origin(ws)
        assert result is False
        ws.close.assert_called_once_with(code=4003, reason="Origin not allowed")

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,http://localhost:3001,tauri://localhost"},
        ),
    )
    @pytest.mark.asyncio
    async def test_wrong_port_rejected(self, _mock_settings: object) -> None:
        """Same host but different port should be rejected."""
        ws = _make_ws(origin="http://localhost:9999")
        result = await verify_ws_origin(ws)
        assert result is False
        ws.close.assert_called_once_with(code=4003, reason="Origin not allowed")

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,https://app.example.com"},
        ),
    )
    @pytest.mark.asyncio
    async def test_https_origin_passes(self, _mock_settings: object) -> None:
        """HTTPS origin in allowlist should pass."""
        ws = _make_ws(origin="https://app.example.com")
        result = await verify_ws_origin(ws)
        assert result is True
        ws.close.assert_not_called()

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000"},
        ),
    )
    @pytest.mark.asyncio
    async def test_empty_origin_string_allows(self, _mock_settings: object) -> None:
        """Empty string Origin (edge case) treated as no Origin."""
        ws = _make_ws(origin="")
        result = await verify_ws_origin(ws)
        assert result is True
        ws.close.assert_not_called()


class TestGetAllowedOrigins:
    """Tests for _get_allowed_origins caching."""

    @pytest.fixture(autouse=True)
    def _clear_cache(self) -> None:
        """Clear lru_cache between tests."""
        _get_allowed_origins.cache_clear()

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type(
            "MockSettings",
            (),
            {"cors_origins": "http://localhost:3000,tauri://localhost"},
        ),
    )
    def test_returns_frozenset(self, _mock_settings: object) -> None:
        """Should return a frozenset for O(1) lookups."""
        result = _get_allowed_origins()
        assert isinstance(result, frozenset)
        assert "http://localhost:3000" in result
        assert "tauri://localhost" in result

    @patch(
        "app.core.infra.ws_origin_guard.settings",
        new_callable=lambda: type("MockSettings", (), {"cors_origins": ""}),
    )
    def test_empty_cors_uses_default(self, _mock_settings: object) -> None:
        """Empty cors_origins should fallback to CORS_ORIGINS_DEFAULT."""
        result = _get_allowed_origins()
        assert "http://localhost:3000" in result
        assert "tauri://localhost" in result
