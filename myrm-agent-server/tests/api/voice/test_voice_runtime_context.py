"""Runtime context injection for voice agent streams (realtime tool-exec + bridge)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.services.agent.execution_cache.types import ExecutionMode

_EXPECTED_CTX = {
    "execution_mode": ExecutionMode.POOLED,
    "disabled_skill_roots": ["skills/prebuilt/off"],
}


def _voice_app() -> FastAPI:
    from app.api.voice.realtime import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1/voice")
    return app


def _providers() -> dict[str, object]:
    return {
        "providers": [
            {
                "id": "openai",
                "apiUrl": "https://api.openai.com/v1",
                "apiKeys": [{"id": "k0", "key": "sk-test", "isActive": True, "remark": ""}],
                "enabledModels": [],
            }
        ],
        "defaultModelConfig": {},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_realtime_tool_exec_injects_runtime_context() -> None:
    mock_configs = MagicMock()
    mock_configs.providers_dict = _providers()
    mock_configs.model_cfg = MagicMock()
    mock_configs.personal_settings_dict = {"enableMemory": True}
    mock_configs.retrieval_dict = {}

    mock_profile = MagicMock()
    mock_profile.enabled_builtin_tools = ("memory",)

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=mock_profile)

    calls: list[dict[str, object]] = []

    async def mock_stream(params, **kwargs):
        calls.append({"params": params, **kwargs})
        yield {"type": "message", "data": "voice-ok"}

    app = _voice_app()
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
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
        patch(
            "app.api.voice.realtime._ensure_model_rebuild_for_tool_exec",
            return_value=None,
        ),
        patch("app.ai_agents.agents.GeneralAgentParams", side_effect=lambda **kw: MagicMock()),
        patch(
            "app.services.agent.runtime_context.build_agent_runtime_context",
            AsyncMock(return_value=dict(_EXPECTED_CTX)),
        ),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            mock_stream,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/voice/realtime-tool-exec",
                json={
                    "tool_name": "web_search",
                    "arguments": {"query": "budget"},
                    "agent_id": "builtin-general",
                },
            )

    assert response.status_code == 200
    assert calls
    assert calls[0]["extra_context"] == _EXPECTED_CTX


@pytest.mark.asyncio
async def test_voice_bridge_consume_injects_runtime_context() -> None:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

    from app.api.voice.agent_bridge import VoiceAgentBridge

    ws = MagicMock()
    ws.send_text = AsyncMock()
    bridge = VoiceAgentBridge(
        _ws=ws,
        _voice_config=MagicMock(),
        _agent_id=None,
        _chat_id="voice-test-1",
    )
    bridge._current_turn = "turn-1"

    calls: list[dict[str, object]] = []

    async def mock_stream(params, **kwargs):
        calls.append({"params": params, **kwargs})
        yield {"type": "tool_use", "data": {"name": "web_search"}}

    with (
        patch(
            "app.services.agent.runtime_context.build_agent_runtime_context",
            AsyncMock(return_value=dict(_EXPECTED_CTX)),
        ),
        patch(
            "app.services.agent.runtime_context.resolve_stream_execution_mode",
            return_value=ExecutionMode.POOLED,
        ),
        patch(
            "app.services.agent.streaming.ai_agent_service_stream",
            mock_stream,
        ),
    ):
        full_text, has_approval = await bridge._consume_agent_stream(
            params=MagicMock(),
            cancel_token=CancellationToken(),
            turn_id="turn-1",
        )

    assert calls
    assert calls[0]["extra_context"] == _EXPECTED_CTX
    assert calls[0]["cancel_token"] is not None
    assert full_text == ""
    assert has_approval is False
