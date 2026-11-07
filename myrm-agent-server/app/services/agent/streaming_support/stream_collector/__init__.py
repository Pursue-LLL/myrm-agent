"""流式内容收集器门面。

[OUTPUT]
StreamContentCollector / ACTIVE_COLLECTORS / settle_tool_approvals_of / _MAX_REASONING_CHARS

[POS]
`app.services.agent.streaming_support.stream_collector` 的唯一入口；实现按 base/handlers/state/core 分层。
"""

from app.services.agent.streaming_support.stream_collector.constants import _MAX_REASONING_CHARS
from app.services.agent.streaming_support.stream_collector.core import (
    ACTIVE_COLLECTORS,
    StreamContentCollector,
    settle_tool_approvals_of,
)

__all__ = [
    "ACTIVE_COLLECTORS",
    "StreamContentCollector",
    "_MAX_REASONING_CHARS",
    "settle_tool_approvals_of",
]
