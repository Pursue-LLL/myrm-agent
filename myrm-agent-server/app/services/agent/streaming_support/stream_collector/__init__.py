"""[INPUT]
- app.services.agent.streaming_support.stream_collector.constants::_MAX_REASONING_CHARS (POS: handlers / state / core 共用的限制与事件映射。)
- app.services.agent.streaming_support.stream_collector.core::ACTIVE_COLLECTORS / StreamContentCollector / release_parked_hitl / settle_tool_approvals_of (POS: Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata, and holds the registry of each chat's parked run; each event type is handled by one `_on_<event type>` method, found through `_EVENT_HANDLERS`.)

[OUTPUT]
- ACTIVE_COLLECTORS
- StreamContentCollector
- release_parked_hitl
- settle_tool_approvals_of

[POS]
`app.services.agent.streaming_support.stream_collector` 的唯一入口；实现按 base/handlers/state/core 分层。
"""

from app.services.agent.streaming_support.stream_collector.constants import _MAX_REASONING_CHARS
from app.services.agent.streaming_support.stream_collector.core import (
    ACTIVE_COLLECTORS,
    StreamContentCollector,
    release_parked_hitl,
    settle_tool_approvals_of,
)

__all__ = [
    "ACTIVE_COLLECTORS",
    "StreamContentCollector",
    "_MAX_REASONING_CHARS",
    "release_parked_hitl",
    "settle_tool_approvals_of",
]
