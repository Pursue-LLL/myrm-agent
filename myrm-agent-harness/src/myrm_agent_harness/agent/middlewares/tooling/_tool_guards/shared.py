"""[INPUT]
- utils.event_utils::dispatch_custom_event (POS: 前端事件分发)

[OUTPUT]
- _emit_loop_guard_event / PreCallResult

[POS]
`_tool_guards/` 的共用事件与阶段间状态；pre/post 两个模块都依赖它。
"""

from __future__ import annotations

from typing import Any

from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord, LoopGuard
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)


async def _emit_loop_guard_event(step_key: str, tool_name: str, loop_kind: str | None, status: str) -> None:
    """Emit a STATUS event to the frontend when LoopGuard triggers WARN/BREAK; it names the kind, not the reason."""
    try:
        from myrm_agent_harness.utils.event_utils import dispatch_custom_event

        await dispatch_custom_event(
            "agent_status",
            {
                "step_key": step_key,
                "tool_name": tool_name,
                "status": status,
                "loop_kind": loop_kind,
            },
        )
    except Exception:
        pass


class PreCallResult:
    """Carries forward state from pre-call guards into the post-call phase."""

    __slots__ = (
        "call_record",
        "loop_guard",
        "loop_verdict",
        "steering_token",
    )

    def __init__(
        self,
        loop_guard: LoopGuard,
        loop_verdict: Any,
        steering_token: Any,
        call_record: CallRecord | None,
    ) -> None:
        self.loop_guard = loop_guard
        self.loop_verdict = loop_verdict
        self.steering_token = steering_token
        self.call_record = call_record
