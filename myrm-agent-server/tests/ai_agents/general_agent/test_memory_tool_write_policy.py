"""Memory write scope follows the channel: external channels are bound-only, web chat may also write shared memory."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchPolicy

from app.ai_agents.general_agent.tool_setup.memory import MemoryToolsMixin
from app.core.memory.adapters.types import ResolvedContextBinding


class _Host(MemoryToolsMixin):
    """The attributes ``_create_memory_tools`` reads from the agent builder."""

    def __init__(self, channel_name: str) -> None:
        self.channel_name = channel_name
        self.agent_id = "agent-1"
        self.embedding_config = None
        self.memory_decay_profile = None
        self.memory_require_confirmation = False
        self.memory_base_path = None
        self.reranker_config = None
        self.enable_advanced_retrieval = False
        self.enable_wiki = False
        self.enable_conversation_search = False
        self.incognito_mode = False
        self._lite_llm = None


async def _policy_handed_to_the_harness(channel_name: str) -> MemorySearchPolicy:
    handed: list[MemorySearchPolicy] = []

    def create_memory_tools(manager: object, *, search_policy: MemorySearchPolicy, **_unused: object) -> list[object]:
        handed.append(search_policy)
        return []

    manager = MagicMock()
    manager.approval_required = False
    binding = ResolvedContextBinding(
        agent_id="agent-1",
        namespaces=[],
        shared_context_ids=[],
        channel_id="channel-1",
        conversation_id="conversation-1",
    )
    with (
        patch("myrm_agent_harness.toolkits.create_memory_tools", create_memory_tools),
        patch("app.core.memory.adapters.setup.create_memory_manager", AsyncMock(return_value=manager)),
        patch("app.core.memory.adapters.setup.create_conflict_callback", MagicMock()),
    ):
        loaded = await _Host(channel_name)._create_memory_tools([], binding)
    # Tool setup degrades to None on any error; that must not pass for a policy it never built.
    assert loaded is manager
    return handed[0]


@pytest.mark.parametrize(
    ("channel_name", "allow_shared_write"),
    [
        pytest.param("web_chat", True, id="web-chat"),
        pytest.param("", True, id="no-channel"),
        pytest.param("telegram", False, id="telegram"),
        pytest.param("wechat", False, id="wechat"),
    ],
)
async def test_only_external_channels_are_kept_off_shared_memory(channel_name: str, allow_shared_write: bool) -> None:
    policy = await _policy_handed_to_the_harness(channel_name)
    assert policy.allow_shared_write is allow_shared_write
