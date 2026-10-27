"""ChannelAgentExecutor helper package — public re-exports.

[INPUT]
- executor_helpers.history (POS: Channel chat history persistence)
- executor_helpers.stream (POS: Stream accumulation for channel turns)
- executor_helpers.quick_replies (POS: Quick-reply suggestions)

[OUTPUT]
Public channel executor helper API: history, stream, and quick-reply symbols.

[POS]
ChannelAgentExecutor 辅助包入口。按关注点拆分为 history / stream / quick_replies。
"""

from __future__ import annotations

from .history import (
    ChannelChatHistory,
    build_chat_history_with_metadata,
    generate_channel_title,
    load_history_without_persist,
    persist_and_load_history,
    persist_assistant_message,
)
from .quick_replies import extract_external_agents, suggest_quick_replies
from .stream import ShareableArtifact, StreamAccumulator, step_to_label

__all__ = [
    "ChannelChatHistory",
    "ShareableArtifact",
    "StreamAccumulator",
    "build_chat_history_with_metadata",
    "extract_external_agents",
    "generate_channel_title",
    "load_history_without_persist",
    "persist_and_load_history",
    "persist_assistant_message",
    "step_to_label",
    "suggest_quick_replies",
]
