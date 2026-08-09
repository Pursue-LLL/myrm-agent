"""Goal stream continuation must inherit chat-bound profile output suffixes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.goal_stream_trigger import _resolve_goal_stream_agent_context
from app.services.agent.profile_resolver import ResolvedAgentProfile


@pytest.mark.asyncio
async def test_resolve_goal_stream_agent_context_applies_ko_formal_suffix() -> None:
    chat = MagicMock()
    chat.agent_id = "builtin-ko-office"

    profile = ResolvedAgentProfile(
        agent_id="builtin-ko-office",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=("web_search",),
        system_prompt="Office assistant base prompt",
        engine_params={
            "response_locale_policy": {
                "locale": "ko-KR",
                "formality": "formal-polite",
            }
        },
    )

    mock_resolver = MagicMock()
    mock_resolver.resolve = AsyncMock(return_value=profile)

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat,
        ),
        patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=mock_resolver,
        ),
    ):
        agent_id, user_instructions = await _resolve_goal_stream_agent_context(
            "chat-session-1"
        )

    assert agent_id == "builtin-ko-office"
    assert user_instructions is not None
    assert user_instructions.startswith("Office assistant base prompt")
    assert "합니다" in user_instructions
    mock_resolver.resolve.assert_awaited_once_with("builtin-ko-office")


@pytest.mark.asyncio
async def test_resolve_goal_stream_agent_context_no_chat_agent() -> None:
    with patch(
        "app.services.chat.chat_service.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
        return_value=None,
    ):
        agent_id, user_instructions = await _resolve_goal_stream_agent_context(
            "chat-session-2"
        )

    assert agent_id is None
    assert user_instructions is None
