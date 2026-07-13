"""ChannelAgentExecutor helper package — public re-exports.

[INPUT]
- executor_helpers.history (POS: Channel chat history persistence)
- executor_helpers.approval (POS: Approval timeout scheduling)
- executor_helpers.stream (POS: Stream accumulation for channel turns)
- executor_helpers.quick_replies (POS: Quick-reply suggestions)

[OUTPUT]
Re-exports all symbols previously available from executor_helpers.py.

[POS]
ChannelAgentExecutor 辅助包入口。按关注点拆分为 history / approval / stream / quick_replies。
"""

from __future__ import annotations

from .approval import notify_channel_timeout_result, schedule_channel_approval_timeout
from .history import (
    build_chat_history_with_metadata,
    generate_channel_title,
    load_history_without_persist,
    persist_and_load_history,
    persist_assistant_message,
)
from .quick_replies import extract_external_agents, suggest_quick_replies
from .stream import ShareableArtifact, StreamAccumulator, step_to_label

__all__ = [
    "ShareableArtifact",
    "StreamAccumulator",
    "build_chat_history_with_metadata",
    "extract_external_agents",
    "generate_channel_title",
    "load_history_without_persist",
    "notify_channel_timeout_result",
    "persist_and_load_history",
    "persist_assistant_message",
    "schedule_channel_approval_timeout",
    "step_to_label",
    "suggest_quick_replies",
]
