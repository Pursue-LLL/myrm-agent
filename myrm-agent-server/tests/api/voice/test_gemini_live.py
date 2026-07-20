"""Unit tests for voice gemini_live endpoints (gemini_live.py).

Covers:
  - _find_google_provider: locating Google/Gemini provider in config
  - _extract_google_api_key: key extraction from various provider configs
  - _build_gemini_tools: tool declaration construction from enabled tools
  - create_gemini_live_token: token generation with mocked config and profile
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.voice.gemini_live import (
    GeminiLiveTokenRequest,
    _build_gemini_tools,
    _extract_google_api_key,
    _find_google_provider,
)


def _providers(
    *,
    provider_id: str = "google",
    keys: tuple[tuple[str, bool], ...] = (("AIza-test-key", True),),
) -> dict[str, object]:
    """Build a providers config mimicking the real persisted shape."""
    return {
        "providers": [
            {
                "id": provider_id,
                "apiUrl": "https://generativelanguage.googleapis.com/v1",
                "apiKeys": [{"id": f"k{i}", "key": k, "isActive": active, "remark": ""} for i, (k, active) in enumerate(keys)],
                "enabledModels": [],
            }
        ],
        "defaultModelConfig": {},
    }


class TestFindGoogleProvider:
    def test_finds_by_google_id(self) -> None:
        assert _find_google_provider(_providers(provider_id="google")) is not None

    def test_finds_by_gemini_id(self) -> None:
        assert _find_google_provider(_providers(provider_id="gemini-pro")) is not None

    def test_returns_none_for_other_provider(self) -> None:
        assert _find_google_provider(_providers(provider_id="openai")) is None

    def test_returns_none_for_empty_providers(self) -> None:
        assert _find_google_provider({}) is None
        assert _find_google_provider({"providers": []}) is None

    def test_skips_non_dict_entries(self) -> None:
        providers = {"providers": ["not-a-dict", _providers(provider_id="google")["providers"][0]]}
        assert _find_google_provider(providers) is not None


class TestExtractGoogleApiKey:
    def test_finds_active_key(self) -> None:
        assert _extract_google_api_key(_providers(keys=(("AIza-active", True),))) == "AIza-active"

    def test_prefers_active_over_inactive(self) -> None:
        providers = _providers(keys=(("AIza-off", False), ("AIza-on", True)))
        assert _extract_google_api_key(providers) == "AIza-on"

    def test_falls_back_to_inactive_when_none_active(self) -> None:
        assert _extract_google_api_key(_providers(keys=(("AIza-only", False),))) == "AIza-only"

    def test_returns_none_when_no_google_provider(self) -> None:
        assert _extract_google_api_key(_providers(provider_id="openai")) is None

    def test_returns_none_for_empty_providers(self) -> None:
        assert _extract_google_api_key({}) is None

    def test_returns_none_when_key_is_empty(self) -> None:
        assert _extract_google_api_key(_providers(keys=(("", True),))) is None

    def test_strips_whitespace(self) -> None:
        assert _extract_google_api_key(_providers(keys=(("  AIza-spaced  ", True),))) == "AIza-spaced"


class TestBuildGeminiTools:
    def test_always_includes_background_task(self) -> None:
        tools = _build_gemini_tools(())
        assert len(tools) == 1
        assert tools[0].name == "run_background_task"

    def test_adds_known_tools(self) -> None:
        tools = _build_gemini_tools(("web_search", "memory"))
        names = [t.name for t in tools]
        assert "run_background_task" in names
        assert "web_search" in names
        assert "memory_search_tool" in names
        assert len(tools) == 3

    def test_ignores_unknown_tools(self) -> None:
        tools = _build_gemini_tools(("web_search", "nonexistent_tool"))
        assert len(tools) == 2

    def test_all_catalog_tools(self) -> None:
        tools = _build_gemini_tools(("web_search", "memory", "file_ops", "code_execute", "browser", "kanban"))
        assert len(tools) == 7


@pytest.mark.asyncio
async def test_create_gemini_live_token_success() -> None:
    from app.api.voice.gemini_live import create_gemini_live_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()

    mock_profile = MagicMock()
    mock_profile.system_prompt = "You are a helpful voice assistant."
    mock_profile.enabled_builtin_tools = ("web_search",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
    ):
        result = await create_gemini_live_token(GeminiLiveTokenRequest(agent_id="test-agent"))

    assert "wss://generativelanguage.googleapis.com" in result.ws_url
    assert "key=AIza-test-key" in result.ws_url
    assert result.model == "gemini-2.5-flash-preview-native-audio-dialog"
    assert result.instructions == "You are a helpful voice assistant."
    assert len(result.tools) == 2


@pytest.mark.asyncio
async def test_create_gemini_live_token_custom_model() -> None:
    from app.api.voice.gemini_live import create_gemini_live_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()

    mock_profile = MagicMock()
    mock_profile.system_prompt = None
    mock_profile.enabled_builtin_tools = ()

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
    ):
        result = await create_gemini_live_token(GeminiLiveTokenRequest(model="gemini-2.0-flash-live-001"))

    assert result.model == "gemini-2.0-flash-live-001"
    assert result.instructions is None


@pytest.mark.asyncio
async def test_create_gemini_live_token_no_api_key() -> None:
    from fastapi import HTTPException

    from app.api.voice.gemini_live import create_gemini_live_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers(provider_id="openai")

    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)):
        with pytest.raises(HTTPException) as exc_info:
            await create_gemini_live_token(GeminiLiveTokenRequest())

    assert exc_info.value.status_code == 400
    assert "Google API key" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_gemini_live_token_no_profile() -> None:
    from app.api.voice.gemini_live import create_gemini_live_token

    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=None)

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=mock_configs)),
        patch("app.services.agent.profile_resolver.get_agent_profile_resolver", return_value=mock_resolver),
    ):
        result = await create_gemini_live_token(GeminiLiveTokenRequest())

    assert result.ws_url.startswith("wss://")
    assert result.instructions is None
    assert len(result.tools) == 1
