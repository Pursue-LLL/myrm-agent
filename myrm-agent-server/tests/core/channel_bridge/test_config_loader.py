"""测试config_parsers中的配置提取逻辑"""

from app.core.channel_bridge.config_parsers import (
    extract_active_search_config as _extract_active_search_config,
)
from app.core.channel_bridge.config_parsers import (
    extract_voice_config,
    extract_web_tts_config,
)


class TestExtractActiveSearchConfig:
    """测试_extract_active_search_config函数"""

    def test_primary_and_fallback_extraction(self):
        """测试提取主服务和备用服务"""
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "role": "primary",
                    "search_service": "tavily",
                    "api_key": "tavily_key",
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

        result = _extract_active_search_config(search_services)

        assert result.search_service == "tavily"
        assert result.api_key == "tavily_key"
        assert result.fallback_config is not None
        assert result.fallback_config.search_service == "searxng"
        assert result.fallback_config.api_base == "http://localhost:8081"

    def test_only_primary_no_fallback(self):
        """测试只有主服务，无备用服务"""
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "role": "primary",
                    "search_service": "tavily",
                    "api_key": "key",
                }
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "tavily"
        assert result.fallback_config is None

    def test_only_fallback_no_primary(self):
        """测试只有备用服务，无主服务（应使用fallback作为primary）"""
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "role": "fallback",
                    "search_service": "searxng",
                }
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "searxng"

    def test_disabled_configs_ignored(self):
        """测试禁用的配置被忽略"""
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": False,
                    "role": "primary",
                    "search_service": "tavily",
                    "api_key": "key",
                },
                {
                    "id": "2",
                    "enabled": True,
                    "role": "fallback",
                    "search_service": "searxng",
                },
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "searxng"
        assert result.fallback_config is not None
        assert result.fallback_config.search_service == "searxng"

    def test_empty_config_returns_none(self):
        """Unconfigured search returns None (no implicit searxng fallback)."""
        result = _extract_active_search_config(None)

        assert result is None

    def test_empty_list_returns_none(self):
        """Empty searchServiceConfigs returns None."""
        search_services = {"searchServiceConfigs": []}

        result = _extract_active_search_config(search_services)

        assert result is None

    def test_no_enabled_configs_returns_none(self):
        """All-disabled configs return None."""
        search_services = {
            "searchServiceConfigs": [
                {"id": "1", "enabled": False, "role": "primary", "search_service": "tavily"},
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result is None

    def test_backward_compatibility_no_role(self):
        """测试向后兼容（无role字段时使用第一个enabled配置）"""
        search_services = {
            "searchServiceConfigs": [
                {"id": "1", "enabled": True, "search_service": "tavily", "api_key": "key"},
                {"id": "2", "enabled": True, "search_service": "perplexity", "api_key": "key2"},
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "tavily"

    def test_multiple_primary_uses_first(self):
        """测试多个primary时使用第一个"""
        search_services = {
            "searchServiceConfigs": [
                {"id": "1", "enabled": True, "role": "primary", "search_service": "tavily", "api_key": "key1"},
                {"id": "2", "enabled": True, "role": "primary", "search_service": "perplexity", "api_key": "key2"},
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "tavily"

    def test_multiple_fallback_uses_first(self):
        """测试多个fallback时使用第一个"""
        search_services = {
            "searchServiceConfigs": [
                {"id": "1", "enabled": True, "role": "primary", "search_service": "tavily", "api_key": "key"},
                {"id": "2", "enabled": True, "role": "fallback", "search_service": "searxng"},
                {"id": "3", "enabled": True, "role": "fallback", "search_service": "perplexity", "api_key": "key2"},
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.search_service == "tavily"
        assert result.fallback_config is not None
        assert result.fallback_config.search_service == "searxng"

    def test_extra_params_preserved(self):
        """测试额外参数被保留"""
        search_services = {
            "searchServiceConfigs": [
                {
                    "id": "1",
                    "enabled": True,
                    "role": "primary",
                    "search_service": "tavily",
                    "api_key": "key",
                    "extra_params": {"search_depth": "advanced", "topic": "news"},
                },
                {
                    "id": "2",
                    "enabled": True,
                    "role": "fallback",
                    "search_service": "searxng",
                    "extra_params": {"engines": ["google", "bing"]},
                },
            ]
        }

        result = _extract_active_search_config(search_services)

        assert result.extra_params == {"search_depth": "advanced", "topic": "news"}
        assert result.fallback_config.extra_params == {"engines": ["google", "bing"]}


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
