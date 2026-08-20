"""Tests for verify_search_service_available with TTL caching."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.channel_bridge.config_parsers import (
    _ping_searxng,
    invalidate_search_health_cache,
    verify_search_service_available,
)


def _make_cfg(service: str = "searxng", api_key: str = "", api_base: str = "") -> SimpleNamespace:
    return SimpleNamespace(search_service=service, api_key=api_key, api_base=api_base, provider_chain=None)


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
    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
        return_value=True,
    ):
        assert await verify_search_service_available(cfg) is True


@pytest.mark.asyncio
async def test_api_key_missing_returns_false() -> None:
    cfg = _make_cfg(service="perplexity", api_key="")
    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
        return_value=False,
    ):
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

    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
    ) as mock_verify:
        mock_verify.return_value = True

        result1 = await verify_search_service_available(cfg)
        result2 = await verify_search_service_available(cfg)

        assert result1 is True
        assert result2 is True
        assert mock_verify.await_count == 2


@pytest.mark.asyncio
async def test_cache_expires_after_ttl() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")

    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
    ) as mock_verify:
        mock_verify.return_value = True

        await verify_search_service_available(cfg)
        assert mock_verify.await_count == 1

        time.sleep(0.15)
        await verify_search_service_available(cfg)
        assert mock_verify.await_count == 2


@pytest.mark.asyncio
async def test_invalidate_cache_forces_recheck() -> None:
    cfg = _make_cfg(api_base="http://localhost:8081")

    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
    ) as mock_verify:
        mock_verify.return_value = True

        await verify_search_service_available(cfg)
        assert mock_verify.await_count == 1

        invalidate_search_health_cache()
        await verify_search_service_available(cfg)
        assert mock_verify.await_count == 2


@pytest.mark.asyncio
async def test_cache_stores_false_result() -> None:
    """Negative results should also be cached via verify_search_config_cached."""
    cfg = _make_cfg(api_base="http://localhost:8081")

    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
    ) as mock_verify:
        mock_verify.return_value = False

        result1 = await verify_search_service_available(cfg)
        result2 = await verify_search_service_available(cfg)

        assert result1 is False
        assert result2 is False
        assert mock_verify.await_count == 2


@pytest.mark.asyncio
async def test_api_key_service_bypasses_cache() -> None:
    """API-key services (non-SearXNG) also go through verify_search_config_cached."""
    cfg = _make_cfg(service="tavily", api_key="sk-key")

    with patch(
        "app.services.integrations.search_verify.verify_search_config_cached",
        new_callable=AsyncMock,
    ) as mock_verify:
        mock_verify.return_value = True
        await verify_search_service_available(cfg)
        await verify_search_service_available(cfg)
        assert mock_verify.await_count == 2


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
        assert policy.notify_on_reset is True

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

    def test_notify_on_reset_false(self) -> None:
        raw = {"mode": "daily", "notify_on_reset": False}
        policy = session_policy_from_agent_dict(raw)
        assert policy.notify_on_reset is False

    def test_notify_on_reset_true_explicit(self) -> None:
        raw = {"mode": "daily", "notify_on_reset": True}
        policy = session_policy_from_agent_dict(raw)
        assert policy.notify_on_reset is True

    def test_notify_on_reset_missing_defaults_true(self) -> None:
        raw = {"mode": "daily"}
        policy = session_policy_from_agent_dict(raw)
        assert policy.notify_on_reset is True


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

    def test_notify_on_reset_false(self) -> None:
        raw = {"sessionPolicy": {"mode": "daily", "notifyOnReset": False}}
        policy = extract_session_policy(raw)
        assert policy.notify_on_reset is False

    def test_notify_on_reset_true(self) -> None:
        raw = {"sessionPolicy": {"mode": "daily", "notifyOnReset": True}}
        policy = extract_session_policy(raw)
        assert policy.notify_on_reset is True

    def test_notify_on_reset_missing_defaults_true(self) -> None:
        raw = {"sessionPolicy": {"mode": "daily"}}
        policy = extract_session_policy(raw)
        assert policy.notify_on_reset is True


class TestExtractVisionFallbackModelConfig:
    def test_returns_none_for_empty_providers(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_config

        assert extract_vision_fallback_model_config(None) is None
        assert extract_vision_fallback_model_config({}) is None

    def test_resolves_vision_fallback_from_default_model_config(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_config

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "providerId": "openai",
                    "model": "gpt-4o-mini",
                }
            },
        }
        cfg = extract_vision_fallback_model_config(providers_dict)
        assert cfg is not None
        assert cfg.model == "openai/gpt-4o-mini"
        assert cfg.api_key == "sk-vision"

    def test_returns_none_when_provider_disabled(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_config

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": False,
                    "apiKeys": [{"key": "sk-vision", "isActive": True}],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "providerId": "openai",
                    "model": "gpt-4o-mini",
                }
            },
        }
        assert extract_vision_fallback_model_config(providers_dict) is None


class TestExtractVisionFallbackModelConfigs:
    def test_builds_chain_with_main_agent_when_vision_capable(self) -> None:
        from app.core.channel_bridge.config_parsers import (
            build_vision_fallback_config_chain,
            extract_vision_fallback_model_configs,
        )
        from app.core.types import ModelConfig

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini", "gpt-4o"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "providerId": "openai",
                    "model": "gpt-4o-mini",
                },
                "baseModel": {
                    "primary": {"providerId": "openai", "model": "gpt-4o"},
                },
            },
        }

        chain = extract_vision_fallback_model_configs(providers_dict)
        assert len(chain) == 2
        assert chain[0].model == "openai/gpt-4o-mini"
        assert chain[1].model == "openai/gpt-4o"

        main_cfg = ModelConfig(
            model="openai/gpt-4o",
            api_key="sk-main",
            supports_vision=True,
        )
        custom_chain = build_vision_fallback_config_chain(
            providers_dict,
            primary_override=chain[0],
            main_model_cfg=main_cfg,
        )
        assert len(custom_chain) == 2
        assert custom_chain[-1].api_key == "sk-main"

    def test_builds_chain_with_model_slot_fallback(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_vision_fallback_model_configs

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini", "gpt-4o"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "primary": {"providerId": "openai", "model": "gpt-4o-mini"},
                    "fallback": {"providerId": "openai", "model": "gpt-4o"},
                },
            },
        }

        chain = extract_vision_fallback_model_configs(providers_dict)
        assert len(chain) == 2
        assert chain[0].model == "openai/gpt-4o-mini"
        assert chain[1].model == "openai/gpt-4o"

    def test_build_vision_fallback_engine_from_providers(self) -> None:
        from app.core.channel_bridge.config_parsers import build_vision_fallback_engine_from_providers

        providers_dict: dict[str, object] = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-vision",
                    "enabledModels": ["gpt-4o-mini"],
                }
            ],
            "defaultModelConfig": {
                "visionFallbackModel": {
                    "primary": {"providerId": "openai", "model": "gpt-4o-mini"},
                },
            },
        }

        engine = build_vision_fallback_engine_from_providers(providers_dict)
        assert engine is not None
        assert len(engine.fallback_configs) == 1
        assert engine.fallback_configs[0].model == "openai/gpt-4o-mini"

    def test_extract_slot_fallback_chain_ordered_and_resilient(self) -> None:
        from app.core.channel_bridge.config_parsers import extract_slot_fallback_chain

        providers_dict = {
            "providers": [
                {
                    "id": "openai",
                    "isEnabled": True,
                    "providerType": "openai",
                    "apiUrl": "https://api.openai.com/v1",
                    "apiKey": "sk-1",
                    "enabledModels": ["gpt-4o"],
                },
                {
                    "id": "anthropic",
                    "isEnabled": False,  # Disabled provider should be skipped
                    "providerType": "anthropic",
                    "apiKey": "sk-2",
                    "enabledModels": ["claude-3-5-sonnet"],
                },
                {
                    "id": "deepseek",
                    "isEnabled": True,
                    "providerType": "deepseek",
                    "apiUrl": "https://api.deepseek.com/v1",
                    "apiKey": "sk-3",
                    "enabledModels": ["deepseek-chat"],
                },
            ],
        }

        slot = {
            "fallbacks": [
                {"providerId": "openai", "model": "gpt-4o"},
                {"providerId": "anthropic", "model": "claude-3-5-sonnet"},
                {"providerId": "deepseek", "model": "deepseek-chat"},
            ]
        }

        configs = extract_slot_fallback_chain(slot, providers_dict)
        assert len(configs) == 2
        assert configs[0].model == "openai/gpt-4o"
        assert configs[1].model == "deepseek/deepseek-chat"


@pytest.mark.asyncio
async def test_verify_search_config_live_skips_e2e_probe_key() -> None:
    from myrm_agent_harness.toolkits.web_search.web_searcher import SearchServiceConfig

    from app.services.integrations.search_verify import verify_search_config_live

    cfg = SearchServiceConfig(
        search_service="tavily",
        api_key="test-tavily-key",
        api_base="",
    )
    assert await verify_search_config_live(cfg) is True
