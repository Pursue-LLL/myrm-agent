"""Memory tool wiring: write scope follows the channel, and the recall mode decides whether any tool is mounted.

External channels are bound-only and web chat may also write shared memory. A context-only run gets the manager
(the injected block needs it) and no memory tool.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchPolicy
from myrm_agent_harness.toolkits.memory.config import RecallMode

from app.ai_agents.general_agent.tool_setup.memory import MemoryToolsMixin
from app.core.memory.adapters.types import ResolvedContextBinding


class _Host(MemoryToolsMixin):
    """The attributes ``_create_memory_tools`` reads from the agent builder."""

    def __init__(self, channel_name: str, recall_mode: RecallMode = RecallMode.HYBRID) -> None:
        self.channel_name = channel_name
        self.memory_recall_mode = recall_mode
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


_BINDING = ResolvedContextBinding(
    agent_id="agent-1",
    namespaces=[],
    shared_context_ids=[],
    channel_id="channel-1",
    conversation_id="conversation-1",
)


async def _mount_memory(recall_mode: RecallMode) -> tuple[list[object], AsyncMock, MagicMock]:
    """Run tool setup for ``recall_mode``: the tools it mounted, the manager factory and the harness tool factory."""
    manager = MagicMock()
    manager.approval_required = False
    create_manager = AsyncMock(return_value=manager)
    create_tools = MagicMock(return_value=["memory_search_tool"])
    mounted: list[object] = []
    with (
        patch("myrm_agent_harness.toolkits.create_memory_tools", create_tools),
        patch("app.core.memory.adapters.setup.create_memory_manager", create_manager),
        patch("app.core.memory.adapters.setup.create_conflict_callback", MagicMock()),
    ):
        loaded = await _Host("web_chat", recall_mode)._create_memory_tools(mounted, _BINDING)
    assert loaded is manager
    return mounted, create_manager, create_tools


async def test_a_context_only_run_gets_the_manager_and_no_memory_tool() -> None:
    mounted, create_manager, create_tools = await _mount_memory(RecallMode.CONTEXT)

    assert mounted == []
    create_tools.assert_not_called()
    assert create_manager.await_args.kwargs["recall_mode"] is RecallMode.CONTEXT


async def test_a_hybrid_run_mounts_the_memory_tools() -> None:
    mounted, create_manager, create_tools = await _mount_memory(RecallMode.HYBRID)

    assert mounted == ["memory_search_tool"]
    create_tools.assert_called_once()
    assert create_manager.await_args.kwargs["recall_mode"] is RecallMode.HYBRID
