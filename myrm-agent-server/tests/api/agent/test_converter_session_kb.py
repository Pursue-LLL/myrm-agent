"""Tests for AgentRequest session_knowledge_base_ids converter integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest, ModelSelection


@pytest.mark.asyncio
async def test_converter_merges_explicit_session_knowledge_base_ids() -> None:
    req = AgentRequest(
        message_id="msg-test-kb-1",
        query="Explain architecture principles",
        agent_id="test-agent",
        chat_id="chat-kb-test",
        action_mode="agent",
        model_selection=ModelSelection(provider_id="mock-prov", model="test-model"),
        session_knowledge_base_ids=["kb-custom-handbook", "kb-engineering-standard"],
    )

    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=None)),
        patch("app.services.agent.params.converter._resolve_model_config", AsyncMock(return_value=None)),
        patch("app.services.agent.params.converter.extract_providers", return_value={"providers": []}),
        patch(
            "app.services.memory.shared_context.shared_context.resolve_shared_context_ids",
            AsyncMock(return_value=["kb-default-profile"]),
        ),
        patch(
            "app.services.memory.shared_context.shared_context.SharedContextService.get_context_names",
            AsyncMock(return_value={}),
        ),
        patch("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=None)),
    ):
        params, *_ = await convert_to_general_agent_params(req, [])

        # Both the profile-resolved shared contexts and explicit session-mounted knowledge bases are merged
        assert "kb-default-profile" in params.memory_shared_context_ids
        assert "kb-custom-handbook" in params.memory_shared_context_ids
        assert "kb-engineering-standard" in params.memory_shared_context_ids
        assert len(params.memory_shared_context_ids) == 3
