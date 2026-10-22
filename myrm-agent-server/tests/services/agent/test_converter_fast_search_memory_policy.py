"""Fast search runs with a conversation-scoped memory policy, handed on as the typed policy object.

The memory binding reads ``policy.agent_id`` and friends off the object, so a plain dict here would raise
``AttributeError`` the moment a fast turn has embeddings configured.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.config import AgentMemoryPolicy, MemoryWritePolicy

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from tests.api.agent.utils import get_model_selection


@pytest.mark.asyncio
async def test_fast_search_hands_on_a_typed_conversation_memory_policy() -> None:
    request = AgentRequest(
        message_id="test-msg-fast-memory-policy",
        chat_id="test-chat-fast-memory-policy",
        query="What changed in Python 3.13?",
        model_selection=get_model_selection(),
        action_mode="fast",
    )

    from tests.api.agent.conftest import _build_mock_user_configs

    with patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=_build_mock_user_configs())):
        params, *_ = await convert_to_general_agent_params(request, [])

    assert params.memory_policy == AgentMemoryPolicy(write_policy=MemoryWritePolicy.CONVERSATION)
