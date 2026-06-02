"""Tests for verify_search_service_available with TTL caching."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.channel_bridge import config_parsers
from app.core.channel_bridge.config_parsers import (
    _ping_searxng,
    invalidate_search_health_cache,
    verify_search_service_available,
)


def _make_cfg(service: str = "searxng", api_key: str = "", api_base: str = "") -> SimpleNamespace:
    return SimpleNamespace(search_service=service, api_key=api_key, api_base=api_base)


def _mock_httpx_client(response: SimpleNamespace | None = None, exc: Exception | None = None) -> AsyncMock:
    mock_client = AsyncMock()
    if exc:
        mock_client.get = AsyncMock(side_effect=exc)
    else:
        mock_client.get = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    """Reset module-level cache before each test."""
    invalidate_search_health_cache()


# ── API-key services ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_key_present_returns_true() -> None:
    cfg = _make_cfg(service="tavily", api_key="sk-123")
    assert await verify_search_service_available(cfg) is True


@pytest.mark.asyncio
async def test_api_key_missing_returns_false() -> None:
    cfg = _make_cfg(service="perplexity", api_key="")
    assert await verify_search_service_available(cfg) is False


# ── _ping_searxng unit tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_ping_searxng_reachable() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")
    mock_client = _mock_httpx_client(SimpleNamespace(status_code=200))

    with patch("httpx.AsyncClient", return_value=mock_client):
        assert await _ping_searxng(cfg) is True


@pytest.mark.asyncio
async def test_ping_searxng_500() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")
    mock_client = _mock_httpx_client(SimpleNamespace(status_code=500))

    with patch("httpx.AsyncClient", return_value=mock_client):
        assert await _ping_searxng(cfg) is False


@pytest.mark.asyncio
async def test_ping_searxng_connection_error() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")
    mock_client = _mock_httpx_client(exc=httpx.ConnectError("refused"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        assert await _ping_searxng(cfg) is False


@pytest.mark.asyncio
async def test_ping_searxng_timeout() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")
    mock_client = _mock_httpx_client(exc=httpx.TimeoutException("timeout"))

    with patch("httpx.AsyncClient", return_value=mock_client):
        assert await _ping_searxng(cfg) is False


@pytest.mark.asyncio
async def test_ping_searxng_no_url_returns_false() -> None:
    cfg = _make_cfg(api_base="")
    assert await _ping_searxng(cfg) is False


# ── TTL cache ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cache_hit_skips_network_call() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")

    with patch.object(config_parsers, "_ping_searxng", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        result1 = await verify_search_service_available(cfg)
        result2 = await verify_search_service_available(cfg)

        assert result1 is True
        assert result2 is True
        assert mock_ping.await_count == 1


@pytest.mark.asyncio
async def test_cache_expires_after_ttl() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")

    with (
        patch.object(config_parsers, "_ping_searxng", new_callable=AsyncMock) as mock_ping,
        patch.object(config_parsers, "_SEARCH_HEALTH_TTL", 0.1),
    ):
        mock_ping.return_value = True

        await verify_search_service_available(cfg)
        assert mock_ping.await_count == 1

        time.sleep(0.15)
        await verify_search_service_available(cfg)
        assert mock_ping.await_count == 2


@pytest.mark.asyncio
async def test_invalidate_cache_forces_recheck() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")

    with patch.object(config_parsers, "_ping_searxng", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = True

        await verify_search_service_available(cfg)
        assert mock_ping.await_count == 1

        invalidate_search_health_cache()
        await verify_search_service_available(cfg)
        assert mock_ping.await_count == 2


@pytest.mark.asyncio
async def test_cache_stores_false_result() -> None:
    """Negative results should also be cached to avoid repeated failing pings."""
    cfg = _make_cfg(api_base="http://localhost:8081")

    with patch.object(config_parsers, "_ping_searxng", new_callable=AsyncMock) as mock_ping:
        mock_ping.return_value = False

        result1 = await verify_search_service_available(cfg)
        result2 = await verify_search_service_available(cfg)

        assert result1 is False
        assert result2 is False
        assert mock_ping.await_count == 1


@pytest.mark.asyncio
async def test_api_key_service_bypasses_cache() -> None:
    """API-key services (non-SearXNG) should not use the cache."""
    cfg = _make_cfg(service="tavily", api_key="sk-key")

    with patch.object(config_parsers, "_ping_searxng", new_callable=AsyncMock) as mock_ping:
        await verify_search_service_available(cfg)
        await verify_search_service_available(cfg)
        mock_ping.assert_not_awaited()


# ── session_policy_from_agent_dict ────────────────────────────────


from app.channels.types import SessionResetMode  # noqa: E402
from app.core.channel_bridge.config_parsers import (  # noqa: E402
    extract_session_policy,
    session_policy_from_agent_dict,
)


class TestSessionPolicyFromAgentDict:
    def test_daily_mode_with_defaults(self) -> None:
        raw = {"mode": "daily", "daily_reset_hour": 4, "idle_minutes": 120}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.DAILY
        assert policy.daily_reset_hour == 4
        assert policy.idle_minutes == 120

    def test_persistent_mode(self) -> None:
        raw = {"mode": "persistent"}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.PERSISTENT
        assert policy.daily_reset_hour == 4
        assert policy.idle_minutes == 120

    def test_idle_mode_custom_minutes(self) -> None:
        raw = {"mode": "idle", "idle_minutes": 30}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.IDLE
        assert policy.idle_minutes == 30

    def test_invalid_mode_falls_back_to_daily(self) -> None:
        raw = {"mode": "nonexistent_mode"}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.DAILY

    def test_missing_mode_defaults_to_daily(self) -> None:
        raw: dict[str, object] = {}
        policy = session_policy_from_agent_dict(raw)
        assert policy.mode == SessionResetMode.DAILY

    def test_float_values_coerced_to_int(self) -> None:
        raw = {"mode": "daily", "daily_reset_hour": 6.0, "idle_minutes": 60.0}
        policy = session_policy_from_agent_dict(raw)
        assert policy.daily_reset_hour == 6
        assert policy.idle_minutes == 60

    def test_custom_reset_hour(self) -> None:
        raw = {"mode": "daily", "daily_reset_hour": 23}
        policy = session_policy_from_agent_dict(raw)
        assert policy.daily_reset_hour == 23


class TestExtractSessionPolicy:
    def test_none_returns_default(self) -> None:
        policy = extract_session_policy(None)
        assert policy.mode == SessionResetMode.DAILY

    def test_missing_key_returns_default(self) -> None:
        policy = extract_session_policy({"other": "data"})
        assert policy.mode == SessionResetMode.DAILY

    def test_valid_policy_parsed(self) -> None:
        raw = {"sessionPolicy": {"mode": "idle", "idleMinutes": 45}}
        policy = extract_session_policy(raw)
        assert policy.mode == SessionResetMode.IDLE
        assert policy.idle_minutes == 45

    def test_persistent_mode(self) -> None:
        raw = {"sessionPolicy": {"mode": "persistent"}}
        policy = extract_session_policy(raw)
        assert policy.mode == SessionResetMode.PERSISTENT
