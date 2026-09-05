"""测试config_parsers中的配置提取逻辑"""

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
    """测试 _inject_provider_oauth_tokens 对各大厂商（含 xAI / Copilot / OpenAI / Anthropic）的注入闭环"""

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
            "provider_openai": {
                "token": "openai-oauth-test-token-67890",
            },
        }

        _inject_provider_oauth_tokens(providers_dict, oauth_creds)

        providers = providers_dict["providers"]
        assert isinstance(providers, list)
        xai_p = next(p for p in providers if p["id"] == "xai")
        assert xai_p["_oauthToken"] == "xai-oauth-test-token-12345"
        assert xai_p["_oauthBaseUrl"] == "https://api.x.ai/v1"

        openai_p = next(p for p in providers if p["id"] == "openai")
        assert openai_p["_oauthToken"] == "openai-oauth-test-token-67890"

    def test_inject_provider_xai_alias(self) -> None:
        from app.core.channel_bridge.config_loader import _inject_provider_oauth_tokens

        providers_dict: dict[str, object] = {
            "providers": [
                {"id": "xai", "name": "xAI", "isEnabled": True, "apiKeys": []},
            ]
        }
        oauth_creds: dict[str, object] = {
            "provider_xai": {
                "token": "xai-oauth-alias-token-99999",
            },
        }

        _inject_provider_oauth_tokens(providers_dict, oauth_creds)

        providers = providers_dict["providers"]
        assert isinstance(providers, list)
        xai_p = next(p for p in providers if p["id"] == "xai")
        assert xai_p["_oauthToken"] == "xai-oauth-alias-token-99999"

