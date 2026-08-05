"""Tests for chat-scoped memory binding resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.memory.adapters.types import ResolvedContextBinding


@pytest.mark.asyncio
async def test_resolve_binding_for_chat_uses_agent_id_and_shared_context() -> None:
    from app.services.context.context_assembly import ContextAssemblyService

    chat = MagicMock()
    chat.id = "chat-marketing"
    chat.agent_id = "agent-marketing"
    chat.project_id = "proj-1"

    profile = MagicMock()
    profile.memory_policy = MagicMock()
    profile.memory_decay_profile = "fast"

    expected_binding = ResolvedContextBinding(
        agent_id="agent-marketing",
        namespaces=["global", "agent:agent-marketing", "shared:ctx-brand"],
        shared_context_ids=["ctx-brand"],
        memory_policy=profile.memory_policy,
        channel_id="web_chat",
        conversation_id="chat-marketing",
    )

    resolver = MagicMock()
    resolver.resolve = AsyncMock(return_value=profile)

    with (
        patch(
            "app.services.chat.chat_service.ChatService.get_chat_metadata",
            new=AsyncMock(return_value=chat),
        ),
        patch(
            "app.services.agent.profile_resolver.get_agent_profile_resolver",
            return_value=resolver,
        ),
        patch(
            "app.services.memory.shared_context.resolve_shared_context_ids",
            new=AsyncMock(return_value=["ctx-brand"]),
        ),
        patch(
            "app.services.context.context_assembly.resolve_context_binding",
            return_value=expected_binding,
        ) as resolve_binding_mock,
    ):
        result = await ContextAssemblyService.resolve_binding_for_chat("chat-marketing")

    resolve_binding_mock.assert_called_once()
    call_kwargs = resolve_binding_mock.call_args.kwargs
    assert call_kwargs["agent_id"] == "agent-marketing"
    assert call_kwargs["channel_id"] == "web_chat"
    assert call_kwargs["conversation_id"] == "chat-marketing"
    assert call_kwargs["shared_context_ids"] == ["ctx-brand"]
    assert call_kwargs["memory_policy"] is profile.memory_policy
    assert result.agent_id == "agent-marketing"
    assert result.memory_decay_profile == "fast"
    assert result.binding is expected_binding
