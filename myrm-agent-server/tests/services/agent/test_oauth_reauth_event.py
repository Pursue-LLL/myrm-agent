"""Tests for _emit_reauth_if_needed dedup, event emission, and refresh_oauth_token failure paths."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.oauth_refresher import (
    _REAUTH_DEDUP_WINDOW_S,
    _emit_reauth_if_needed,
    _reauth_emitted_at,
)


def _reset_dedup() -> None:
    _reauth_emitted_at.clear()


_PATCH_TARGET = "app.services.event.app_event_bus.get_event_bus"


def test_emit_publishes_event() -> None:
    """First call for an issuer should publish OAUTH_REAUTH_REQUIRED."""
    _reset_dedup()
    mock_bus = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_bus):
        _emit_reauth_if_needed("google_workspace", "invalid_grant")

    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.event_type.value == "oauth_reauth_required"
    assert event.data["issuer"] == "google_workspace"
    assert event.data["reason"] == "invalid_grant"


def test_dedup_suppresses_within_window() -> None:
    """Second call within the dedup window should NOT publish."""
    _reset_dedup()
    mock_bus = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_bus):
        _emit_reauth_if_needed("google_workspace", "invalid_grant")
        _emit_reauth_if_needed("google_workspace", "invalid_grant")

    assert mock_bus.publish.call_count == 1


def test_dedup_allows_different_issuers() -> None:
    """Different issuers should each get their own event."""
    _reset_dedup()
    mock_bus = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_bus):
        _emit_reauth_if_needed("google_workspace", "expired")
        _emit_reauth_if_needed("slack_oauth", "expired")

    assert mock_bus.publish.call_count == 2


def test_dedup_allows_after_window_expires() -> None:
    """After the dedup window, a new event should be published."""
    _reset_dedup()
    mock_bus = MagicMock()
    with patch(_PATCH_TARGET, return_value=mock_bus):
        _emit_reauth_if_needed("google_workspace", "expired")
        _reauth_emitted_at["google_workspace"] = time.time() - _REAUTH_DEDUP_WINDOW_S - 1
        _emit_reauth_if_needed("google_workspace", "expired")

    assert mock_bus.publish.call_count == 2


def test_publish_failure_is_graceful() -> None:
    """If publish raises, the function should not propagate the exception."""
    _reset_dedup()
    mock_bus = MagicMock()
    mock_bus.publish.side_effect = RuntimeError("bus is down")
    with patch(_PATCH_TARGET, return_value=mock_bus):
        _emit_reauth_if_needed("test_issuer", "fail_reason")

    assert "test_issuer" in _reauth_emitted_at


# ---------------------------------------------------------------------------
# Integration: refresh_oauth_token failure paths → _emit_reauth_if_needed
# ---------------------------------------------------------------------------

class _FakeAsyncCtx:
    """Minimal async context manager that wraps a session mock."""

    def __init__(self, session: MagicMock) -> None:
        self._session = session

    async def __aenter__(self) -> MagicMock:
        return self._session

    async def __aexit__(self, *args: object) -> None:
        pass


def _build_session_with_cred(cred_val: dict) -> MagicMock:
    """Build a mock get_session() that returns a row with the given credential."""
    row = MagicMock()
    row.config_value = {"test_issuer": cred_val}
    row.is_encrypted = False

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = row
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars

    session = AsyncMock()
    session.execute.return_value = mock_result

    return MagicMock(return_value=_FakeAsyncCtx(session))


@pytest.mark.asyncio
async def test_refresh_missing_refresh_token_emits_reauth() -> None:
    """When refresh_token is absent, should emit OAUTH_REAUTH_REQUIRED."""
    _reset_dedup()
    mock_get_session = _build_session_with_cred({"token": "old", "token_url": "https://example.com/token"})

    mock_bus = MagicMock()
    with (
        patch("app.services.agent.oauth_refresher.get_session", mock_get_session),
        patch("app.services.agent.oauth_refresher.get_encryption_service"),
        patch(_PATCH_TARGET, return_value=mock_bus),
    ):
        from app.services.agent.oauth_refresher import refresh_oauth_token

        result = await refresh_oauth_token("test_issuer")

    assert result is None
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.data["reason"] == "missing_refresh_token"


@pytest.mark.asyncio
async def test_refresh_4xx_response_emits_reauth() -> None:
    """When OAuth provider returns 4xx, should emit OAUTH_REAUTH_REQUIRED."""
    _reset_dedup()
    mock_get_session = _build_session_with_cred({
        "token": "old",
        "refresh_token": "rt_123",
        "token_url": "https://example.com/token",
        "expires_at": time.time() - 100,
    })

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"
    mock_resp.json.return_value = {"error": "invalid_grant", "error_description": "Token revoked"}

    mock_bus = MagicMock()
    with (
        patch("app.services.agent.oauth_refresher.get_session", mock_get_session),
        patch("app.services.agent.oauth_refresher.get_encryption_service"),
        patch("httpx.AsyncClient.post", return_value=mock_resp),
        patch(_PATCH_TARGET, return_value=mock_bus),
    ):
        from app.services.agent.oauth_refresher import refresh_oauth_token

        result = await refresh_oauth_token("test_issuer")

    assert result is None
    mock_bus.publish.assert_called_once()
    event = mock_bus.publish.call_args[0][0]
    assert event.data["reason"] == "Token revoked"


@pytest.mark.asyncio
async def test_refresh_5xx_response_does_not_emit_reauth() -> None:
    """When OAuth provider returns 5xx (server error), should NOT emit reauth."""
    _reset_dedup()
    mock_get_session = _build_session_with_cred({
        "token": "old",
        "refresh_token": "rt_123",
        "token_url": "https://example.com/token",
        "expires_at": time.time() - 100,
    })

    mock_resp = MagicMock()
    mock_resp.status_code = 503
    mock_resp.text = "Service Unavailable"

    mock_bus = MagicMock()
    with (
        patch("app.services.agent.oauth_refresher.get_session", mock_get_session),
        patch("app.services.agent.oauth_refresher.get_encryption_service"),
        patch("httpx.AsyncClient.post", return_value=mock_resp),
        patch(_PATCH_TARGET, return_value=mock_bus),
    ):
        from app.services.agent.oauth_refresher import refresh_oauth_token

        result = await refresh_oauth_token("test_issuer")

    assert result is None
    mock_bus.publish.assert_not_called()


@pytest.mark.asyncio
async def test_refresh_network_exception_does_not_emit_reauth() -> None:
    """When network fails entirely, should NOT emit reauth (transient error)."""
    _reset_dedup()
    mock_get_session = _build_session_with_cred({
        "token": "old",
        "refresh_token": "rt_123",
        "token_url": "https://example.com/token",
        "expires_at": time.time() - 100,
    })

    import httpx

    mock_bus = MagicMock()
    with (
        patch("app.services.agent.oauth_refresher.get_session", mock_get_session),
        patch("app.services.agent.oauth_refresher.get_encryption_service"),
        patch("httpx.AsyncClient.post", side_effect=httpx.ConnectError("Connection refused")),
        patch(_PATCH_TARGET, return_value=mock_bus),
    ):
        from app.services.agent.oauth_refresher import refresh_oauth_token

        result = await refresh_oauth_token("test_issuer")

    assert result is None
    mock_bus.publish.assert_not_called()
