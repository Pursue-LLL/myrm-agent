"""Unit tests for voice realtime endpoints (realtime.py).

Covers:
  - _extract_openai_api_key: key extraction from various provider configs
  - _extract_openai_base_url: base URL extraction with normalization
  - _safe_json_str: safe serialization
  - create_realtime_token: token generation with mocked httpx and config
  - execute_realtime_tool: tool proxy with mocked agent stream
  - persist_realtime_transcript: transcript persistence
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.voice.realtime import (
    RealtimeTokenRequest,
    RealtimeToolExecRequest,
    RealtimeTranscriptRequest,
    _extract_openai_api_key,
    _extract_openai_base_url,
    _find_openai_provider,
    _safe_json_str,
)
from app.api.voice.tool_catalog import build_realtime_tools
from app.api.voice.voice_memory_context import VoiceMemoryContext

_ALL_MEMORY = VoiceMemoryContext(enable_memory=True, enable_conversation_search=True, enable_wiki=True)
_MEMORY_ONLY = VoiceMemoryContext(enable_memory=True, enable_conversation_search=False, enable_wiki=False)

# ── shared fixtures ───────────────────────────────────────────────────


def _providers(
    *,
    provider_id: str = "openai",
    api_url: str = "https://api.openai.com/v1",
    keys: tuple[tuple[str, bool], ...] = (("sk-test", True),),
) -> dict[str, object]:
    """Build a providers config in the real persisted shape (see frontend providerTypes.ts)."""
    return {
        "providers": [
            {
                "id": provider_id,
                "apiUrl": api_url,
                "apiKeys": [{"id": f"k{i}", "key": k, "isActive": active, "remark": ""} for i, (k, active) in enumerate(keys)],
                "enabledModels": [],
            }
        ],
        "defaultModelConfig": {},
    }


# ── _find_openai_provider tests ───────────────────────────────────────


class TestFindOpenaiProvider:
    def test_finds_by_openai_id(self) -> None:
        assert _find_openai_provider(_providers(provider_id="openai")) is not None

    def test_finds_by_openai_variant(self) -> None:
        assert _find_openai_provider(_providers(provider_id="openai-custom")) is not None

    def test_returns_none_for_other_provider(self) -> None:
        assert _find_openai_provider(_providers(provider_id="anthropic")) is None

    def test_returns_none_for_empty(self) -> None:
        assert _find_openai_provider({}) is None
        assert _find_openai_provider({"providers": []}) is None

    def test_skips_non_dict_entries(self) -> None:
        providers = {
            "providers": [
                42,
                "string",
                _providers(provider_id="openai")["providers"][0],
            ]
        }
        assert _find_openai_provider(providers) is not None


# ── _extract_openai_api_key tests ─────────────────────────────────────


class TestExtractOpenaiApiKey:
    def test_finds_active_key(self) -> None:
        assert _extract_openai_api_key(_providers(keys=(("sk-test-123", True),))) == "sk-test-123"

    def test_prefers_active_over_inactive(self) -> None:
        providers = _providers(keys=(("sk-off", False), ("sk-on", True)))
        assert _extract_openai_api_key(providers) == "sk-on"

    def test_falls_back_to_inactive_when_none_active(self) -> None:
        assert _extract_openai_api_key(_providers(keys=(("sk-only", False),))) == "sk-only"

    def test_matches_openai_in_id(self) -> None:
        assert _extract_openai_api_key(_providers(provider_id="openai-main")) == "sk-test"

    def test_returns_none_when_no_openai_provider(self) -> None:
        assert _extract_openai_api_key(_providers(provider_id="anthropic")) is None

    def test_returns_none_for_empty_providers(self) -> None:
        assert _extract_openai_api_key({}) is None
        assert _extract_openai_api_key({"providers": []}) is None

    def test_skips_non_dict_entries(self) -> None:
        providers = {"providers": ["not-a-dict", _providers()["providers"][0]]}
        assert _extract_openai_api_key(providers) == "sk-test"

    def test_returns_none_when_key_is_empty(self) -> None:
        assert _extract_openai_api_key(_providers(keys=(("", True),))) is None


# ── _extract_openai_base_url tests ────────────────────────────────────


class TestExtractOpenaiBaseUrl:
    def test_extracts_api_url(self) -> None:
        assert _extract_openai_base_url(_providers(api_url="https://proxy.example.com/v1/")) == ("https://proxy.example.com/v1")

    def test_strips_trailing_slash(self) -> None:
        assert _extract_openai_base_url(_providers(api_url="https://api.example.com/")) == "https://api.example.com"

    def test_returns_none_for_empty_url(self) -> None:
        assert _extract_openai_base_url(_providers(api_url="  ")) is None

    def test_returns_none_when_no_openai_provider(self) -> None:
        assert _extract_openai_base_url(_providers(provider_id="anthropic")) is None


# ── _safe_json_str tests ──────────────────────────────────────────────


class TestSafeJsonStr:
    def test_serializes_dict(self) -> None:
        result = _safe_json_str({"a": 1, "b": "hello"})
        assert '"a": 1' in result
        assert '"b": "hello"' in result

    def test_handles_non_serializable(self) -> None:
        class Custom:
            def __str__(self) -> str:
                return "custom-obj"

        result = _safe_json_str({"key": Custom()})
        assert "custom-obj" in result

    def test_handles_empty_dict(self) -> None:
        assert _safe_json_str({}) == "{}"


# ── build_realtime_tools tests ───────────────────────────────────────


class TestBuildRealtimeTools:
    def test_always_includes_background_lifecycle_tools(self) -> None:
        tools = build_realtime_tools((), _MEMORY_ONLY)
        names = {t.name for t in tools}
        assert "run_background_task" in names
        assert "get_background_tasks_status" in names
        assert "cancel_background_task" in names
        assert "steer_background_task" in names
        assert "set_reminder" in names
        assert "cancel_reminder" in names
        assert "list_reminders" in names
        assert len(tools) == 7

    def test_adds_known_tools(self) -> None:
        tools = build_realtime_tools(("web_search", "memory"), _ALL_MEMORY)
        names = [t.name for t in tools]
        assert "run_background_task" in names
        assert "web_search" in names
        assert "memory_search_tool" in names
        assert len(tools) == 9

    def test_memory_tool_omits_sessions_when_opt_in_off(self) -> None:
        tools = build_realtime_tools(("memory",), _MEMORY_ONLY)
        memory_tool = next(t for t in tools if t.name == "memory_search_tool")
        corpus_prop = memory_tool.parameters.get("properties", {}).get("corpus")
        assert corpus_prop is None

    def test_memory_tool_includes_sessions_when_opt_in_on(self) -> None:
        tools = build_realtime_tools(("memory",), _ALL_MEMORY)
        memory_tool = next(t for t in tools if t.name == "memory_search_tool")
        corpus_enum = memory_tool.parameters["properties"]["corpus"]["enum"]
        assert "sessions" in corpus_enum
        assert "all" in corpus_enum

    def test_skips_memory_tool_when_memory_disabled(self) -> None:
        disabled = VoiceMemoryContext(enable_memory=False, enable_conversation_search=False, enable_wiki=False)
        tools = build_realtime_tools(("memory", "web_search"), disabled)
        names = [t.name for t in tools]
        assert "memory_search_tool" not in names
        assert "web_search" in names

    def test_ignores_unknown_tools(self) -> None:
        tools = build_realtime_tools(("web_search", "nonexistent_tool"), _MEMORY_ONLY)
        assert len(tools) == 8

    def test_all_catalog_tools(self) -> None:
        tools = build_realtime_tools(
            ("web_search", "memory", "file_ops", "code_execute", "browser", "kanban"),
            _ALL_MEMORY,
        )
        assert len(tools) == 13

    def test_render_ui_not_exposed_even_when_profile_enabled(self) -> None:
        """Voice Realtime has no inline A2UI surface — catalog omits render_ui (see gemini_live)."""
        tools = build_realtime_tools(("web_search", "render_ui", "kanban"), _MEMORY_ONLY)
        names = [t.name for t in tools]
        assert "render_ui" not in names
        assert "web_search" in names
        assert "kanban" in names

    def test_tool_structure_valid(self) -> None:
        tools = build_realtime_tools(("web_search",), _MEMORY_ONLY)
        ws_tool = next(t for t in tools if t.name == "web_search")
        assert ws_tool.type == "function"
        assert ws_tool.description
        assert "properties" in ws_tool.parameters
        assert "required" in ws_tool.parameters


# ── create_realtime_token endpoint tests ──────────────────────────────


@pytest.mark.asyncio
async def test_create_realtime_token_success() -> None:
    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers(api_url="https://api.openai.com/v1")
    mock_configs.voice_dict = {"ttsVoice": "alloy"}
    mock_configs.model_cfg = MagicMock()

    mock_profile = MagicMock()
    mock_profile.model = "gpt-realtime-2"
    mock_profile.system_prompt = "You are a helpful assistant."
    mock_profile.enabled_builtin_tools = ("web_search",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"client_secret": {"value": "ek-test-secret", "expires_at": 1717000000}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await create_realtime_token(RealtimeTokenRequest(agent_id="test-agent"))

    assert result.client_secret == "ek-test-secret"
    assert result.model == "gpt-realtime-2"
    assert result.voice == "alloy"
    assert result.expires_at == 1717000000
    assert result.instructions == "You are a helpful assistant."
    assert len(result.tools) >= 1
    assert any(t.name == "run_background_task" for t in result.tools)
    # The sessions URL is built from the configured apiUrl (which carries /v1) — never a second /v1.
    assert mock_client.post.await_args.args[0] == "https://api.openai.com/v1/realtime/sessions"
    assert mock_client.post.await_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"
    posted_payload = mock_client.post.await_args.kwargs["json"]
    assert "tools" in posted_payload


@pytest.mark.asyncio
async def test_create_realtime_token_no_profile_returns_default_tools() -> None:
    """When profile is None, only run_background_task should appear in tools."""
    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.voice_dict = {}
    mock_configs.model_cfg = MagicMock()

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=None)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"client_secret": {"value": "ek-secret", "expires_at": None}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await create_realtime_token(RealtimeTokenRequest())

    assert len(result.tools) == 7
    assert any(t.name == "run_background_task" for t in result.tools)
    assert any(t.name == "set_reminder" for t in result.tools)
    assert result.instructions is None
    assert result.voice == "verse"


@pytest.mark.asyncio
async def test_create_realtime_token_voice_from_config() -> None:
    """Voice should come from voice_dict when not in request."""
    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.voice_dict = {"ttsVoice": "coral"}
    mock_configs.model_cfg = MagicMock()

    mock_profile = MagicMock()
    mock_profile.model = None
    mock_profile.system_prompt = None
    mock_profile.enabled_builtin_tools = ()

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"client_secret": {"value": "ek-s", "expires_at": None}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await create_realtime_token(RealtimeTokenRequest())

    assert result.voice == "coral"


@pytest.mark.asyncio
async def test_create_realtime_token_invalid_voice_uses_default() -> None:
    """If configured voice is not in REALTIME_VOICES, use default."""
    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.voice_dict = {"ttsVoice": "invalid-voice-name"}
    mock_configs.model_cfg = MagicMock()

    mock_profile = MagicMock()
    mock_profile.model = None
    mock_profile.system_prompt = None
    mock_profile.enabled_builtin_tools = ()

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"client_secret": {"value": "ek-s", "expires_at": None}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await create_realtime_token(RealtimeTokenRequest())

    assert result.voice == "verse"


@pytest.mark.asyncio
async def test_create_realtime_token_tools_payload_format() -> None:
    """Verify the exact format of tools in the OpenAI sessions payload."""
    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.voice_dict = {}
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {"enableMemory": True}

    mock_profile = MagicMock()
    mock_profile.model = None
    mock_profile.system_prompt = None
    mock_profile.enabled_builtin_tools = ("web_search", "memory")

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"client_secret": {"value": "ek-s", "expires_at": None}}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        await create_realtime_token(RealtimeTokenRequest())

    posted_payload = mock_client.post.await_args.kwargs["json"]
    tools_payload = posted_payload["tools"]
    assert len(tools_payload) == 6
    for tool in tools_payload:
        assert "type" in tool
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert tool["type"] == "function"


@pytest.mark.asyncio
async def test_create_realtime_token_no_api_key() -> None:
    from fastapi import HTTPException

    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers(provider_id="anthropic")
    mock_configs.voice_dict = {}

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(return_value=mock_configs),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_realtime_token(RealtimeTokenRequest())

    assert exc_info.value.status_code == 400
    assert "OpenAI API key" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_realtime_token_openai_error() -> None:
    from fastapi import HTTPException

    from app.api.voice.realtime import create_realtime_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.voice_dict = {}
    mock_configs.model_cfg = MagicMock()

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=None)

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await create_realtime_token(RealtimeTokenRequest())

    assert exc_info.value.status_code == 502


# ── persist_realtime_transcript endpoint tests ────────────────────────


@pytest.mark.asyncio
async def test_persist_transcript_success() -> None:
    from app.api.voice.realtime import persist_realtime_transcript

    mock_append = AsyncMock()
    with patch("app.services.chat.ChatService.append_message", mock_append):
        result = await persist_realtime_transcript(
            RealtimeTranscriptRequest(
                chat_id="chat-123",
                entries=[
                    {"role": "user", "text": "Hello"},
                    {"role": "assistant", "text": "Hi there!"},
                    {"role": "user", "text": ""},
                ],
            )
        )

    assert result == {"ok": True}
    assert mock_append.call_count == 2


@pytest.mark.asyncio
async def test_persist_transcript_skips_empty() -> None:
    from app.api.voice.realtime import persist_realtime_transcript

    mock_append = AsyncMock()
    with patch("app.services.chat.ChatService.append_message", mock_append):
        result = await persist_realtime_transcript(
            RealtimeTranscriptRequest(
                chat_id="chat-123",
                entries=[
                    {"role": "user", "text": "   "},
                    {"role": "assistant", "text": "  \n  "},
                ],
            )
        )

    assert result == {"ok": True}
    assert mock_append.call_count == 0


# ── execute_realtime_tool endpoint tests ──────────────────────────────


@pytest.mark.asyncio
async def test_execute_tool_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {
        "enableMemory": True,
        "memoryEnableConversationSearch": True,
    }
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory", "wiki")

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    captured: dict[str, object] = {}

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    async def mock_stream(params, **kwargs):
        yield {"type": "message", "data": "result: sunny"}

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_lite_model_config",
            return_value=None,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_retrieval_models",
            return_value=(None, None),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.api.voice.realtime._ensure_model_rebuild_for_tool_exec",
            return_value=None,
        ),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=capture_params),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="memory_search_tool",
                arguments={"query": "deployment", "corpus": "sessions"},
                agent_id="builtin-general",
            )
        )

    assert result.error is None
    assert "sunny" in str(result.result)
    assert captured.get("enable_conversation_search") is True
    assert captured.get("enable_memory") is True
    assert captured.get("enable_wiki") is True


@pytest.mark.asyncio
async def test_execute_tool_honors_disabled_conversation_search() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {"enableMemory": True}
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    captured: dict[str, object] = {}

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    async def mock_stream(params, **kwargs):
        yield {"type": "message", "data": "ok"}

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_lite_model_config",
            return_value=None,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_retrieval_models",
            return_value=(None, None),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.api.voice.realtime._ensure_model_rebuild_for_tool_exec",
            return_value=None,
        ),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=capture_params),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="memory_search_tool",
                arguments={"query": "budget", "corpus": "sessions"},
            )
        )

    assert result.error is None
    assert captured.get("enable_memory") is True
    assert captured.get("enable_conversation_search") is False


@pytest.mark.asyncio
async def test_execute_tool_honors_net_fetch_gate() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {"enableMemory": False}
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory",)
    mock_profile.security_overrides = {"capabilities": ["file_read"]}

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    captured: dict[str, object] = {}

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    async def mock_stream(params, **kwargs):
        yield {"type": "message", "data": "ok"}

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_lite_model_config",
            return_value=None,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_retrieval_models",
            return_value=(None, None),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.api.voice.realtime._ensure_model_rebuild_for_tool_exec",
            return_value=None,
        ),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=capture_params),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="memory_search_tool",
                arguments={"query": "budget", "corpus": "memory"},
            )
        )

    assert result.error is None
    assert captured.get("enable_web_fetch") is False
    assert captured.get("agent_security_raw") == {"capabilities": ["file_read"]}


@pytest.mark.asyncio
async def test_execute_tool_failure() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(side_effect=RuntimeError("Config error")),
    ):
        result = await execute_realtime_tool(RealtimeToolExecRequest(tool_name="failing_tool", arguments={}))

    assert result.error is not None
    assert result.error == "Tool execution failed"


@pytest.mark.asyncio
async def test_execute_tool_rejects_unsafe_chat_id() -> None:
    """A malicious chat_id must fail fast with 400 before any agent work."""
    from fastapi import HTTPException

    from app.api.voice.realtime import execute_realtime_tool

    with patch(
        "app.services.agent.streaming.ai_agent_service_stream",
        AsyncMock(side_effect=AssertionError("agent must not run")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await execute_realtime_tool(
                RealtimeToolExecRequest(
                    tool_name="memory_search_tool",
                    arguments={"query": "x"},
                    chat_id="../../etc/passwd",
                )
            )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_execute_tool_accepts_safe_chat_id() -> None:
    """A legitimate chat_id passes the whitelist guard and reaches the agent."""
    from app.api.voice.realtime import execute_realtime_tool

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {"enableMemory": False}
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    captured: dict[str, object] = {}

    def capture_params(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return MagicMock()

    async def mock_stream(params, **kwargs):
        yield {"type": "message", "data": "ok"}

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            AsyncMock(return_value=mock_configs),
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_lite_model_config",
            return_value=None,
        ),
        patch(
            "app.core.channel_bridge.config_parsers.extract_retrieval_models",
            return_value=(None, None),
        ),
        patch(
            "app.services.agent.profile.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.api.voice.realtime._ensure_model_rebuild_for_tool_exec",
            return_value=None,
        ),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=capture_params),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="memory_search_tool",
                arguments={"query": "budget"},
                chat_id="voice-abc123",
            )
        )

    assert result.error is None
    assert captured.get("chat_id") == "voice-abc123"


@pytest.mark.asyncio
async def test_run_background_task_spawns_without_agent_stream() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_handler = MagicMock()
    mock_handler.spawn_background = AsyncMock(return_value="voice-task-abc")

    with (
        patch(
            "app.core.channel_bridge.setup.get_background_task_handler",
            return_value=mock_handler,
        ),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            AsyncMock(side_effect=AssertionError("must not invoke agent stream")),
        ),
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="run_background_task",
                arguments={"task": "Research competitor pricing"},
                agent_id="builtin-general",
                chat_id="chat-voice-1",
            )
        )

    assert result.error is None
    assert result.result is not None
    payload = json.loads(str(result.result))
    assert payload["accepted"] is True
    assert payload["work_id"] == "voice-task-abc"
    mock_handler.spawn_background.assert_awaited_once()
    _args, kwargs = mock_handler.spawn_background.await_args
    assert kwargs.get("background_source") == "voice"
    assert kwargs.get("agent_id") == "builtin-general"


@pytest.mark.asyncio
async def test_run_background_task_requires_task_text() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    result = await execute_realtime_tool(
        RealtimeToolExecRequest(
            tool_name="run_background_task",
            arguments={"task": "   "},
        )
    )
    assert result.error == "Task description is required"


@pytest.mark.asyncio
async def test_persist_transcript_error_raises() -> None:
    from fastapi import HTTPException

    from app.api.voice.realtime import persist_realtime_transcript

    with patch(
        "app.services.chat.ChatService.append_message",
        AsyncMock(side_effect=RuntimeError("DB down")),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await persist_realtime_transcript(
                RealtimeTranscriptRequest(
                    chat_id="chat-err",
                    entries=[{"role": "user", "text": "Hello"}],
                )
            )
    assert exc_info.value.status_code == 500


# ── chat_id empty defense (C) ────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_background_task_rejects_empty_chat_id() -> None:
    """When chat_id is None, the endpoint must return an error instead of using fallback."""
    from app.api.voice.realtime import execute_realtime_tool

    result = await execute_realtime_tool(
        RealtimeToolExecRequest(
            tool_name="run_background_task",
            arguments={"task": "Do some research"},
            chat_id=None,
        )
    )
    assert result.error is not None
    assert "chat" in result.error.lower()


# ── cancel_background_task tool tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_cancel_background_task_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_handler = MagicMock()
    mock_handler.cancel_background = AsyncMock(return_value=True)

    with patch(
        "app.core.channel_bridge.setup.get_background_task_handler",
        return_value=mock_handler,
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="cancel_background_task",
                arguments={"task_id": "task-abc"},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["cancelled"] is True
    assert payload["task_id"] == "task-abc"


@pytest.mark.asyncio
async def test_cancel_background_task_not_found() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_handler = MagicMock()
    mock_handler.cancel_background = AsyncMock(return_value=False)

    with patch(
        "app.core.channel_bridge.setup.get_background_task_handler",
        return_value=mock_handler,
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="cancel_background_task",
                arguments={"task_id": "nonexist"},
                chat_id="chat-1",
            )
        )

    assert result.error is not None
    assert "not found" in result.error.lower() or "not cancellable" in result.error.lower()


@pytest.mark.asyncio
async def test_cancel_background_task_missing_task_id() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    result = await execute_realtime_tool(
        RealtimeToolExecRequest(
            tool_name="cancel_background_task",
            arguments={},
            chat_id="chat-1",
        )
    )
    assert result.error is not None
    assert "task_id" in result.error.lower()


# ── get_background_tasks_status tool tests ────────────────────────────


@pytest.mark.asyncio
async def test_get_background_tasks_status_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool
    from app.channels.protocols.background_task import BackgroundTaskInfo

    mock_handler = MagicMock()
    mock_handler.list_background = AsyncMock(
        return_value=[
            BackgroundTaskInfo(
                task_id="t1",
                prompt="Research competitors",
                status="running",
                created_at=1717000000.0,
            ),
            BackgroundTaskInfo(
                task_id="t2",
                prompt="Write report",
                status="completed",
                created_at=1717000100.0,
                completed_at=1717000200.0,
                result_preview="Report generated successfully",
            ),
        ]
    )

    with patch(
        "app.core.channel_bridge.setup.get_background_task_handler",
        return_value=mock_handler,
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="get_background_tasks_status",
                arguments={},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["count"] == 2
    assert len(payload["tasks"]) == 2

    t1 = payload["tasks"][0]
    assert t1["task_id"] == "t1"
    assert t1["completed_at"] is None
    assert t1["result_preview"] is None

    t2 = payload["tasks"][1]
    assert t2["task_id"] == "t2"
    assert t2["completed_at"] == 1717000200.0
    assert t2["result_preview"] == "Report generated successfully"


@pytest.mark.asyncio
async def test_get_background_tasks_status_empty() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_handler = MagicMock()
    mock_handler.list_background = AsyncMock(return_value=[])

    with patch(
        "app.core.channel_bridge.setup.get_background_task_handler",
        return_value=mock_handler,
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="get_background_tasks_status",
                arguments={},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["count"] == 0
    assert payload["tasks"] == []


# ── steer_background_task tool tests ──────────────────────────────────


@pytest.mark.asyncio
async def test_steer_background_task_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_handler = MagicMock()
    mock_handler.steer_background = AsyncMock(return_value=True)

    with patch(
        "app.core.channel_bridge.setup.get_background_task_handler",
        return_value=mock_handler,
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="steer_background_task",
                arguments={"task_id": "task-abc", "instruction": "Focus on security"},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["steered"] is True
    assert payload["task_id"] == "task-abc"


@pytest.mark.asyncio
async def test_steer_background_task_not_found() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_handler = MagicMock()
    mock_handler.steer_background = AsyncMock(return_value=False)

    with patch(
        "app.core.channel_bridge.setup.get_background_task_handler",
        return_value=mock_handler,
    ):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="steer_background_task",
                arguments={"task_id": "nonexist", "instruction": "Redirect"},
                chat_id="chat-1",
            )
        )

    assert result.error is not None


@pytest.mark.asyncio
async def test_steer_background_task_missing_args() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    result = await execute_realtime_tool(
        RealtimeToolExecRequest(
            tool_name="steer_background_task",
            arguments={"task_id": "abc"},
            chat_id="chat-1",
        )
    )
    assert result.error is not None
    assert "instruction" in result.error.lower()


# ── set_reminder / cancel_reminder / list_reminders tool tests ─────────


@pytest.mark.asyncio
async def test_set_reminder_minutes_later_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    mock_mgr = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "job-reminder-123"
    mock_job.name = "Voice Reminder: Drink water"
    mock_mgr.create_job = AsyncMock(return_value=mock_job)

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_mgr):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="set_reminder",
                arguments={"content": "Drink water", "minutes_later": 10},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["success"] is True
    assert payload["job_id"] == "job-reminder-123"
    assert "Drink water" in payload["name"]
    assert mock_mgr.create_job.call_count == 1
    call_kwargs = mock_mgr.create_job.call_args.kwargs
    assert call_kwargs["prompt"] == "Drink water"
    assert call_kwargs["chat_id"] == "chat-1"


@pytest.mark.asyncio
async def test_set_reminder_missing_content() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    result = await execute_realtime_tool(
        RealtimeToolExecRequest(
            tool_name="set_reminder",
            arguments={"minutes_later": 5},
            chat_id="chat-1",
        )
    )
    assert result.error is not None
    assert "content is required" in result.error.lower()


@pytest.mark.asyncio
async def test_cancel_reminder_by_id_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool
    from myrm_agent_harness.toolkits.cron.types import JobStatus, JobType

    mock_mgr = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "rem-1"
    mock_job.name = "Voice Reminder: Meeting"
    mock_job.prompt = "Meeting"
    mock_job.status = JobStatus.ACTIVE
    mock_job.job_type = JobType.REMINDER

    mock_mgr.list_jobs = AsyncMock(return_value=[mock_job])
    mock_mgr.delete_job = AsyncMock(return_value=True)

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_mgr):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="cancel_reminder",
                arguments={"reminder_id": "rem-1"},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["cancelled"] is True
    assert payload["job_id"] == "rem-1"
    assert mock_mgr.delete_job.call_count == 1


@pytest.mark.asyncio
async def test_cancel_reminder_not_found() -> None:
    from app.api.voice.realtime import execute_realtime_tool
    from myrm_agent_harness.toolkits.cron.types import JobStatus, JobType

    mock_mgr = MagicMock()
    mock_mgr.list_jobs = AsyncMock(return_value=[])

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_mgr):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="cancel_reminder",
                arguments={"content": "Nonexistent reminder"},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["cancelled"] is False
    assert "No matching" in payload["message"]


@pytest.mark.asyncio
async def test_list_reminders_success() -> None:
    from app.api.voice.realtime import execute_realtime_tool
    from myrm_agent_harness.toolkits.cron.types import JobStatus, JobType
    from datetime import datetime, timezone

    mock_mgr = MagicMock()
    mock_job = MagicMock()
    mock_job.id = "rem-1"
    mock_job.name = "Voice Reminder: Stretch"
    mock_job.prompt = "Stretch"
    mock_job.status = JobStatus.ACTIVE
    mock_job.job_type = JobType.REMINDER
    mock_job.next_run_at = datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc)

    mock_mgr.list_jobs = AsyncMock(return_value=[mock_job])

    with patch("app.core.cron.adapters.setup.get_cron_manager", return_value=mock_mgr):
        result = await execute_realtime_tool(
            RealtimeToolExecRequest(
                tool_name="list_reminders",
                arguments={},
                chat_id="chat-1",
            )
        )

    assert result.error is None
    payload = json.loads(str(result.result))
    assert payload["count"] == 1
    assert len(payload["reminders"]) == 1
    assert payload["reminders"][0]["id"] == "rem-1"
    assert payload["reminders"][0]["content"] == "Stretch"

