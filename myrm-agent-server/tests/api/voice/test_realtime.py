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

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.voice.realtime import (
    REALTIME_VOICES,
    RealtimeTokenRequest,
    RealtimeToolExecRequest,
    RealtimeTranscriptRequest,
    _build_realtime_tools,
    _extract_openai_api_key,
    _extract_openai_base_url,
    _find_openai_provider,
    _safe_json_str,
)

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
        providers = {"providers": [42, "string", _providers(provider_id="openai")["providers"][0]]}
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


# ── _build_realtime_tools tests ───────────────────────────────────────


class TestBuildRealtimeTools:
    def test_always_includes_background_task(self) -> None:
        tools = _build_realtime_tools(())
        assert len(tools) == 1
        assert tools[0].name == "run_background_task"

    def test_adds_known_tools(self) -> None:
        tools = _build_realtime_tools(("web_search", "memory"))
        names = [t.name for t in tools]
        assert "run_background_task" in names
        assert "web_search" in names
        assert "memory_recall" in names
        assert len(tools) == 3

    def test_ignores_unknown_tools(self) -> None:
        tools = _build_realtime_tools(("web_search", "nonexistent_tool"))
        assert len(tools) == 2

    def test_all_catalog_tools(self) -> None:
        tools = _build_realtime_tools(("web_search", "memory", "file_ops", "code_execute", "browser", "kanban"))
        assert len(tools) == 7

    def test_render_ui_not_exposed_even_when_profile_enabled(self) -> None:
        """Voice Realtime has no inline A2UI surface — catalog omits render_ui (see gemini_live)."""
        tools = _build_realtime_tools(("web_search", "render_ui", "kanban"))
        names = [t.name for t in tools]
        assert "render_ui" not in names
        assert "web_search" in names
        assert "kanban" in names

    def test_tool_structure_valid(self) -> None:
        tools = _build_realtime_tools(("web_search",))
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
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
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
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await create_realtime_token(RealtimeTokenRequest())

    assert len(result.tools) == 1
    assert result.tools[0].name == "run_background_task"
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
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
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
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
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
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        result = await create_realtime_token(RealtimeTokenRequest())

    posted_payload = mock_client.post.await_args.kwargs["json"]
    tools_payload = posted_payload["tools"]
    assert len(tools_payload) == 3
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

    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)):
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
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
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
                entries=[{"role": "user", "text": "   "}, {"role": "assistant", "text": "  \n  "}],
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

    async def mock_stream(params):
        yield {"type": "message", "data": "result: sunny"}
        yield {"type": "message", "data": " 25°C"}

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.core.channel_bridge.config_parsers.extract_lite_model_config", return_value=None),
        patch("app.api.voice.realtime._ensure_model_rebuild_for_tool_exec", return_value=None),
        patch("app.ai_agents.agents.GeneralAgentParams", MagicMock()),
        patch("app.services.agent.streaming.ai_agent_service_stream", mock_stream),
    ):
        result = await execute_realtime_tool(RealtimeToolExecRequest(tool_name="weather", arguments={"city": "Tokyo"}))

    assert result.error is None
    assert "sunny" in str(result.result)


@pytest.mark.asyncio
async def test_execute_tool_failure() -> None:
    from app.api.voice.realtime import execute_realtime_tool

    with patch(
        "app.core.channel_bridge.config_loader.load_user_configs",
        AsyncMock(side_effect=RuntimeError("Config error")),
    ):
        result = await execute_realtime_tool(RealtimeToolExecRequest(tool_name="failing_tool", arguments={}))

    assert result.error is not None
    assert "Config error" in result.error


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
