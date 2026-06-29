"""Integration: notify_targets propagation through convert_to_general_agent_params."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.models import AgentRequest
from app.services.agent.profile_resolver import ResolvedAgentProfile


@pytest.fixture
def base_request() -> dict:
    return {
        "message_id": "test-msg-notify",
        "chat_id": "test-chat-notify",
        "query": "hello",
        "model_selection": {
            "providerId": "minimax",
            "model": os.environ.get("BASIC_MODEL", "minimax/MiniMax-M2.7"),
            "baseUrl": os.environ.get("BASIC_BASE_URL", "https://api.minimaxi.com/v1"),
        },
        "agent_config": {
            "enabledBuiltinTools": ["web_search"],
        },
    }


def _resolved_with_notify() -> ResolvedAgentProfile:
    return ResolvedAgentProfile(
        agent_id="notify-agent-1",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=("web_search",),
        system_prompt="You are a notifier.",
        model="openai/gpt-4o-mini",
        notify_targets=(
            {"channel": "telegram", "recipient_id": "chat_1", "label": "Alerts"},
        ),
    )


class TestNotifyTargetsConverterIntegration:
    @pytest.mark.asyncio
    async def test_notify_targets_propagate_in_normal_mode(self, base_request: dict) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=_resolved_with_notify())

        base_request["agent_id"] = "notify-agent-1"
        base_request["action_mode"] = "agent"
        request = AgentRequest(**base_request)

        with patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ):
            params, _, _, _ = await convert_to_general_agent_params(request, [])
            mock_resolver.resolve.assert_awaited_once_with("notify-agent-1")

        assert params.notify_targets == (
            {"channel": "telegram", "recipient_id": "chat_1", "label": "Alerts"},
        )

    @pytest.mark.asyncio
    async def test_fast_search_clears_notify_targets(self, base_request: dict) -> None:
        from app.services.agent.params.converter import convert_to_general_agent_params

        mock_resolver = AsyncMock()
        mock_resolver.resolve = AsyncMock(return_value=_resolved_with_notify())

        base_request["action_mode"] = "fast"
        base_request["agent_id"] = "notify-agent-1"
        request = AgentRequest(**base_request)

        with patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ):
            params, _, _, _ = await convert_to_general_agent_params(request, [])
            mock_resolver.resolve.assert_awaited_once_with("notify-agent-1")

        assert params.notify_targets == ()
