"""测试config_parsers中的配置提取逻辑"""

import time
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.config_parsers import (
    extract_active_search_config as _extract_active_search_config,
)
from app.core.channel_bridge.config_parsers import (
    extract_search_provider_chain,
    extract_voice_config,
    extract_web_tts_config,
)


class TestExtractActiveSearchConfig:
    """测试_extract_active_search_config函数（priority chain）"""

    def test_priority_chain_extraction(self):
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "tavily",
                    "api_key": "tavily_key",
                },
                {
                    "id": "2",
                    "enabled": True,
                    "priority": 2,
                    "search_service": "searxng",
                    "api_base": "http://localhost:8081",
                },
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result is not None
        assert result.search_service == "tavily"
        assert result.api_key == "tavily_key"
        assert result.provider_chain is not None
        assert len(result.provider_chain) == 2
        assert result.provider_chain[0].search_service == "tavily"
        assert result.provider_chain[1].search_service == "searxng"
        assert result.provider_chain[1].api_base == "http://localhost:8081"

    def test_only_single_provider(self):
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "tavily",
                    "api_key": "key",
                }
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result is not None
        assert result.search_service == "tavily"
        assert result.provider_chain is not None
        assert len(result.provider_chain) == 1

    def test_legacy_role_migration(self):
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "role": "primary",
                    "search_service": "tavily",
                    "api_key": "key",
                },
                {
                    "id": "2",
                    "enabled": True,
                    "role": "fallback",
                    "search_service": "searxng",
                    "api_base": "http://localhost:8081",
                },
            ]
        }

        chain = extract_search_provider_chain(search_services)
        assert len(chain) == 2
        assert chain[0].search_service == "tavily"
        assert chain[1].search_service == "searxng"

    def test_disabled_configs_ignored(self):
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": False,
                    "priority": 1,
                    "search_service": "tavily",
                    "api_key": "key",
                },
                {
                    "id": "2",
                    "enabled": True,
                    "priority": 2,
                    "search_service": "searxng",
                },
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result is not None
        assert result.search_service == "searxng"
        assert result.provider_chain is not None
        assert len(result.provider_chain) == 1

    def test_empty_config_returns_none(self):
        result = _extract_active_search_config(None)
        assert result is None

    def test_empty_list_returns_none(self):
        search_services = {"searchServiceConfigs": []}
        result = _extract_active_search_config(search_services)
        assert result is None

    def test_no_enabled_configs_returns_none(self):
        search_services = {
            "searchServiceConfigs": [
                {"id": "1", "enabled": False, "priority": 1, "search_service": "tavily"},
            ]
        }
        result = _extract_active_search_config(search_services)
        assert result is None

    def test_priority_sorting(self):
        search_services = {
            "searchServiceConfigs": [
                {"id": "1", "enabled": True, "priority": 3, "search_service": "perplexity", "api_key": "k"},
                {"id": "2", "enabled": True, "priority": 1, "search_service": "tavily", "api_key": "k1"},
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result is not None
        assert result.search_service == "tavily"
        assert result.provider_chain is not None
        assert result.provider_chain[0].search_service == "tavily"
        assert result.provider_chain[1].search_service == "perplexity"

    def test_extra_params_preserved(self):
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "priority": 1,
                    "search_service": "tavily",
                    "api_key": "key",
                    "extra_params": {"search_depth": "advanced", "topic": "news"},
                },
                {
                    "id": "2",
                    "enabled": True,
                    "priority": 2,
                    "search_service": "searxng",
                    "extra_params": {"engines": ["google", "bing"]},
                },
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result is not None
        assert result.extra_params == {"search_depth": "advanced", "topic": "news"}
        assert result.provider_chain is not None
        assert result.provider_chain[1].extra_params == {"engines": ["google", "bing"]}


class TestExtractVoiceConfig:
    """测试extract_voice_config函数的local STT字段解析"""

    def test_local_stt_fields_parsed(self) -> None:
        voice_dict: dict[str, object] = {
            "sttEnabled": True,
            "sttProvider": "local",
            "sttLocalModel": "small",
            "sttLocalDevice": "cuda",
            "sttLocalComputeType": "float16",
        }
        result = extract_voice_config(voice_dict)
        assert result is not None
        assert result.stt_provider == "local"
        assert result.stt_local_model == "small"
        assert result.stt_local_device == "cuda"
        assert result.stt_local_compute_type == "float16"

    def test_local_stt_defaults(self) -> None:
        voice_dict: dict[str, object] = {"sttEnabled": True, "sttProvider": "local"}
        result = extract_voice_config(voice_dict)
        assert result is not None
        assert result.stt_local_model == "base"
        assert result.stt_local_device == "auto"
        assert result.stt_local_compute_type == "auto"

    def test_cloud_stt_preserves_api_key(self) -> None:
        voice_dict: dict[str, object] = {
            "sttEnabled": True,
            "sttProvider": "openai",
            "sttApiKey": "sk-test",
            "sttModel": "whisper-1",
        }
        result = extract_voice_config(voice_dict)
        assert result is not None
        assert result.stt_provider == "openai"
        assert result.stt_api_key == "sk-test"

    def test_none_when_both_disabled(self) -> None:
        voice_dict: dict[str, object] = {"sttEnabled": False, "ttsMode": "off"}
        result = extract_voice_config(voice_dict)
        assert result is None

    def test_none_for_empty_dict(self) -> None:
        result = extract_voice_config(None)
        assert result is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(1.5, 1.5), (2, 2.0), ("0.8", 0.8), ("fast", 1.0), (None, 1.0)],
    )
    def test_tts_speed_falls_back_to_default_when_not_a_number(self, raw: object, expected: float) -> None:
        result = extract_voice_config({"ttsMode": "always", "ttsSpeed": raw})
        assert result is not None
        assert result.tts_speed == expected

    @pytest.mark.parametrize(("raw", "expected"), [("zh", "zh"), (7, None), (None, None)])
    def test_stt_language_only_accepts_text(self, raw: object, expected: str | None) -> None:
        result = extract_voice_config({"sttEnabled": True, "sttLanguage": raw})
        assert result is not None
        assert result.stt_language == expected


class TestExtractWebTtsConfig:
    """Web /tts uses extract_web_tts_config — ignores channel ttsMode gate."""

    def test_returns_config_when_tts_mode_off(self) -> None:
        voice_dict: dict[str, object] = {
            "sttEnabled": False,
            "ttsMode": "off",
            "ttsProvider": "edge",
        }
        channel = extract_voice_config(voice_dict)
        web = extract_web_tts_config(voice_dict)
        assert channel is None
        assert web is not None
        assert web.tts_provider == "edge"
        assert web.tts_mode.value == "off"

    def test_none_for_empty_dict(self) -> None:
        assert extract_web_tts_config(None) is None


class TestInjectProviderOAuthTokens:
    """测试 _inject_provider_oauth_tokens：仅 xAI SuperGrok 订阅 token 会注入到 provider 配置"""

    def test_inject_xai_oauth_token_and_base_url(self) -> None:
        from app.core.channel_bridge.config_loader import _inject_provider_oauth_tokens

        providers_dict: dict[str, object] = {
            "providers": [
                {"id": "xai", "name": "xAI", "isEnabled": True, "apiKeys": []},
                {"id": "openai", "name": "OpenAI", "isEnabled": True, "apiKeys": []},
            ]
        }
        oauth_creds: dict[str, object] = {
            "xai": {
                "token": "xai-oauth-test-token-12345",
                "base_url": "https://api.x.ai/v1",
            },
        }

        _inject_provider_oauth_tokens(providers_dict, oauth_creds)

        providers = providers_dict["providers"]
        assert isinstance(providers, list)
        xai_p = next(p for p in providers if p["id"] == "xai")
        assert xai_p["_oauthToken"] == "xai-oauth-test-token-12345"
        assert xai_p["_oauthBaseUrl"] == "https://api.x.ai/v1"

        openai_p = next(p for p in providers if p["id"] == "openai")
        assert "_oauthToken" not in openai_p

    def test_inject_xai_oauth_token_without_base_url(self) -> None:
        from app.core.channel_bridge.config_loader import _inject_provider_oauth_tokens

        providers_dict: dict[str, object] = {"providers": [{"id": "xai", "isEnabled": True, "apiKeys": []}]}

        _inject_provider_oauth_tokens(providers_dict, {"xai": {"token": "xai-oauth-token"}})

        providers = providers_dict["providers"]
        assert isinstance(providers, list)
        assert providers[0]["_oauthToken"] == "xai-oauth-token"
        assert "_oauthBaseUrl" not in providers[0]

    @pytest.mark.parametrize(
        ("issuer", "provider_id"),
        [
            ("provider_anthropic", "anthropic"),
            ("provider_openai", "openai"),
            ("provider_copilot", "copilot"),
        ],
    )
    def test_retired_subscription_issuers_are_never_injected(self, issuer: str, provider_id: str) -> None:
        """Tokens stored under retired provider issuers (Claude / ChatGPT / Copilot) are never injected as API keys."""
        from app.core.channel_bridge.config_loader import _inject_provider_oauth_tokens

        providers_dict: dict[str, object] = {"providers": [{"id": provider_id, "isEnabled": True, "apiKeys": []}]}

        _inject_provider_oauth_tokens(providers_dict, {issuer: {"token": "leftover-token"}})

        providers = providers_dict["providers"]
        assert isinstance(providers, list)
        assert "_oauthToken" not in providers[0]


class _FakeSession:
    """Stands in for ``get_session()``: yields the seeded UserConfig rows."""

    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def execute(self, statement: object) -> MagicMock:
        result = MagicMock()
        result.scalars.return_value.all.return_value = self._rows
        return result


def _row(key: str, value: object) -> SimpleNamespace:
    return SimpleNamespace(config_key=key, config_value=value, is_encrypted=False)


def _subscription_rows(
    oauth_entry: dict[str, object], *, api_keys: list[dict[str, object]] | None = None
) -> list[SimpleNamespace]:
    return [
        _row("providers", {"providers": [{"id": "xai", "isEnabled": True, "apiKeys": api_keys or []}]}),
        _row("defaultModelConfig", {"baseModel": {"primary": {"providerId": "xai", "model": "grok-4"}}}),
        _row("oauthCredentials", {"xai": oauth_entry}),
    ]


def _oauth_entry(token: str, *, expires_in: float) -> dict[str, object]:
    return {
        "token": token,
        "refresh_token": "rt_1",
        "token_url": "https://auth.x.ai/oauth2/token",
        "base_url": "https://api.x.ai/v1",
        "expires_at": time.time() + expires_in,
    }


@pytest.fixture(autouse=True)
def mock_load_user_configs() -> Iterator[None]:
    """Run the real loader: the suite-wide autouse mock would hide everything tested here."""
    yield


@pytest.fixture
def fresh_config_cache() -> Iterator[None]:
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache

    invalidate_user_configs_cache()
    yield
    invalidate_user_configs_cache()


@pytest.mark.usefixtures("fresh_config_cache")
class TestLoadUserConfigsSubscriptionTokens:
    """load_user_configs resolves the default model from subscription tokens, renewed when due."""

    @staticmethod
    async def _load(rows: list[SimpleNamespace], refresh: AsyncMock) -> object:
        from app.core.channel_bridge.config_loader import load_user_configs

        with (
            patch("app.database.connection.get_session", lambda: _FakeSession(rows)),
            patch("app.services.agent.provider_oauth_tokens.refresh_oauth_token", refresh),
        ):
            return await load_user_configs()

    @pytest.mark.asyncio
    async def test_subscription_only_user_resolves_the_default_model(self) -> None:
        refresh = AsyncMock()

        configs = await self._load(_subscription_rows(_oauth_entry("subscription-token", expires_in=3600)), refresh)

        assert configs.model_cfg.api_key == "subscription-token"
        assert configs.model_cfg.model == "xai/grok-4"
        assert configs.model_cfg.base_url == "https://api.x.ai/v1"
        refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expiring_token_is_renewed_before_it_is_handed_out(self) -> None:
        refresh = AsyncMock(return_value=SimpleNamespace(token="renewed-token", expires_at=time.time() + 3600))

        configs = await self._load(_subscription_rows(_oauth_entry("stale-token", expires_in=60)), refresh)

        refresh.assert_awaited_once_with("xai")
        assert configs.model_cfg.api_key == "renewed-token"
        assert configs.oauth_credentials_dict["xai"]["token"] == "renewed-token"
        assert configs.providers_dict["providers"][0]["_oauthToken"] == "renewed-token"

    @pytest.mark.asyncio
    async def test_failed_renewal_still_loads_with_the_stored_token(self) -> None:
        refresh = AsyncMock(return_value=None)

        configs = await self._load(_subscription_rows(_oauth_entry("stale-token", expires_in=60)), refresh)

        assert configs.model_cfg.api_key == "stale-token"

    @pytest.mark.asyncio
    async def test_users_own_api_key_keeps_priority_over_the_subscription(self) -> None:
        rows = _subscription_rows(
            _oauth_entry("subscription-token", expires_in=3600),
            api_keys=[{"key": "sk-user", "isActive": True}],
        )

        configs = await self._load(rows, AsyncMock())

        assert configs.model_cfg.api_key == "sk-user"

    @pytest.mark.asyncio
    async def test_without_a_connected_subscription_nothing_is_refreshed(self) -> None:
        rows = [
            row
            for row in _subscription_rows({}, api_keys=[{"key": "sk-user", "isActive": True}])
            if row.config_key != "oauthCredentials"
        ]
        refresh = AsyncMock()

        configs = await self._load(rows, refresh)

        assert configs.model_cfg.api_key == "sk-user"
        refresh.assert_not_awaited()
