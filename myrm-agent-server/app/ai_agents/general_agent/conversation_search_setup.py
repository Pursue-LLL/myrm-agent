"""Conversation search tool assembly for GeneralAgent.

[INPUT]
app.services.chat.conversation_search_service::ConversationHistorySearchProvider (POS: 会话历史召回服务)
myrm_agent_harness.toolkits.memory.conversation_search::create_conversation_search_tool (POS: framework-level conversation recall tool factory)

[OUTPUT]
append_conversation_search_tool: Attach the read-only conversation_search tool to eager tools for GeneralAgent.

[POS]
GeneralAgent 会话搜索装配辅助模块。与 memory_recall 对称 eager 挂载，稳定 tools 前缀以利 prompt cache。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory.conversation_search import create_conversation_search_tool
from myrm_agent_harness.toolkits.memory.manager import MemoryManager

from app.services.chat.conversation_search_service import ConversationHistorySearchProvider

logger = logging.getLogger(__name__)


def append_conversation_search_tool(
    tools: list[object],
    *,
    current_chat_id: str | None,
    agent_id: str | None,
    memory_manager: MemoryManager | None,
) -> None:
    """Attach conversation_search to GeneralAgent eager tools."""

    provider = ConversationHistorySearchProvider(
        current_chat_id=current_chat_id,
        agent_id=agent_id,
        memory_manager=memory_manager,
    )
    tools.append(create_conversation_search_tool(provider))
    logger.debug(
        "Loaded conversation_search tool [Eager] (chat_id=%s, agent_id=%s)",
        current_chat_id or "",
        agent_id or "",
    )
