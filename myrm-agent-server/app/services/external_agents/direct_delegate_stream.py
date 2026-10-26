"""Direct delegation: one external-agent turn streamed to the frontend as SSE events.

[INPUT]
- myrm_agent_harness.api::AgentEventType (POS: 前端 SSE 事件类型), on_token_cancelled (POS: 令牌取消时从外部终止阻塞的流)
- myrm_agent_harness.toolkits.acp.types (POS: 外部 Agent 委托协议：运行时事件、错误码、委托池)

[OUTPUT]
- stream_direct_delegate: harness RuntimeEvent 流 → 前端 SSE 事件流

[POS]
绕过 LangChain Agent 的外部 Agent 直连路由的事件翻译层。每次外部工具调用是一个带 tool_call_id 的独立步骤
（开始与结果落在同一步）；会话没有被续接时发一个只有标题的步骤，措辞由前端按当前语言给出。停止（令牌取消）
经 pool.cancel 终止外部进程，外部 Agent 静默时同样即时生效。
"""

from __future__ import annotations

from contextlib import aclosing
from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias

from myrm_agent_harness.api import AgentEventType, on_token_cancelled
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode, ContinuityStatus, RuntimeEventType

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Mapping

    from myrm_agent_harness.toolkits.acp.types import DelegationPool, RuntimeEvent
    from myrm_agent_harness.utils import CancellationToken

SseEvent: TypeAlias = dict[str, object]

# A failed tool call shows the start of the text it failed with, not the whole output.
_MAX_TOOL_ERROR_CHARS = 300


class _Outcome(StrEnum):
    """How a delegated turn ended, as far as the stream could tell."""

    COMPLETED = "completed"
    TURN_LIMIT = "turn_limit"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _token_count(value: object) -> int:
    """Usage payload values are loosely typed; anything that is not a plain number counts as 0."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return int(value)


class _TurnTranslator:
    """Turns the RuntimeEvents of one delegated turn into frontend events.

    Remembers what later events need: the line of every tool call that has started (its result updates the same
    step) and how the turn ended.
    """

    def __init__(self, agent_name: str, auth_mode: str) -> None:
        self._agent = agent_name
        self._auth_mode = auth_mode
        self._source = f"delegate:{agent_name}"
        self._tool_lines: dict[str, str] = {}
        self.outcome = _Outcome.COMPLETED

    def connecting(self) -> SseEvent:
        return self._status_step("connecting")

    def translate(self, event: RuntimeEvent) -> list[SseEvent]:
        data = event.data
        match event.type:
            case RuntimeEventType.TEXT_DELTA:
                content = data.get("content")
                return [{"type": AgentEventType.MESSAGE.value, "data": content}] if isinstance(content, str) else []
            case RuntimeEventType.REASONING_DELTA:
                content = data.get("content")
                if not isinstance(content, str):
                    return []
                return [
                    {
                        "type": AgentEventType.REASONING.value,
                        "data": {"content": content, "source": self._source},
                    }
                ]
            case RuntimeEventType.TOOL_START:
                return [self._tool_started(data)]
            case RuntimeEventType.TOOL_RESULT:
                return [self._tool_finished(data)]
            case RuntimeEventType.STATUS_UPDATE:
                return [self._status_update(data)]
            case RuntimeEventType.USAGE_UPDATE:
                return self._usage(data)
            case RuntimeEventType.ERROR:
                return self._error(data)
            case _:
                return []

    def closing(self) -> list[SseEvent]:
        """The final status line and the end of the message (a cancelled turn has neither)."""
        match self.outcome:
            case _Outcome.TURN_LIMIT:
                status = self._status_step("stopped at its turn limit", state="completed")
            case _Outcome.FAILED:
                status = self._status_step("failed", state="error")
            case _:
                status = self._status_step("completed", state="completed")
        return [status, {"type": AgentEventType.MESSAGE_END.value, "data": ""}]

    def _status_step(self, text: str, *, state: str | None = None) -> SseEvent:
        event: SseEvent = {
            "type": AgentEventType.TASKS_STEPS.value,
            "step_key": f"delegation_{self._agent}_status",
            "tool_name": self._source,
            "data": [{"text": f"{self._agent}: {text}"}],
        }
        if state:
            event["status"] = state
        return event

    def _tool_step(self, call_id: str, line: str, *, state: str | None = None, error: str | None = None) -> SseEvent:
        # Every update resends the line: the frontend replaces a step's items with whatever the update carries.
        event: SseEvent = {
            "type": AgentEventType.TASKS_STEPS.value,
            "step_key": f"delegation_{self._agent}_tool",
            "tool_name": self._source,
            "data": [{"text": line}],
        }
        if call_id:
            event["tool_call_id"] = call_id
        if state:
            event["status"] = state
        if error:
            event["error"] = error
        return event

    def _tool_started(self, data: Mapping[str, object]) -> SseEvent:
        summary = data.get("summary")
        line = f"{self._agent}: {data.get('tool_name') or 'unknown'}" + (f" — {summary}" if summary else "")
        call_id = str(data.get("tool_call_id") or "")
        self._tool_lines[call_id] = line
        return self._tool_step(call_id, line)

    def _tool_finished(self, data: Mapping[str, object]) -> SseEvent:
        call_id = str(data.get("tool_call_id") or "")
        output = data.get("output")
        text = output.strip() if isinstance(output, str) else ""
        line = self._tool_lines.pop(call_id, None)
        if line is None:
            # A result with no start (a file change some CLIs report only once it is done) describes itself.
            line = f"{self._agent}: tool" + (f" — {text.splitlines()[0]}" if text else "")
        if data.get("is_error"):
            return self._tool_step(call_id, line, state="error", error=text[:_MAX_TOOL_ERROR_CHARS])
        return self._tool_step(call_id, line, state="completed")

    def _status_update(self, data: Mapping[str, object]) -> SseEvent:
        status = data.get("status", "")
        continuity = ContinuityStatus.of(status)
        if continuity is not None:
            # A notice the UI words itself (title only), not a step that is still running.
            return {
                "type": AgentEventType.TASKS_STEPS.value,
                "step_key": f"delegation_{self._agent}_{continuity}",
                "tool_name": self._source,
                "status": "completed",
                "data": [],
            }
        message = data.get("message", "")
        return self._status_step(f"{status}" + (f" — {message}" if message else ""))

    def _usage(self, data: Mapping[str, object]) -> list[SseEvent]:
        input_tokens = _token_count(data.get("input_tokens"))
        output_tokens = _token_count(data.get("output_tokens"))
        total_tokens = input_tokens + output_tokens
        if total_tokens <= 0:
            return []
        return [
            {
                "type": AgentEventType.TOKEN_USAGE.value,
                "data": {
                    "source": self._source,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens,
                    # Subscription runs on the user's own plan → no metered API cost.
                    "auth_mode": self._auth_mode,
                    "billable": self._auth_mode == "api_key",
                },
            }
        ]

    def _error(self, data: Mapping[str, object]) -> list[SseEvent]:
        error = data.get("error")
        code = getattr(error, "code", None)
        if code is AcpErrorCode.CANCELLED:
            self.outcome = _Outcome.CANCELLED
            return []
        if code is AcpErrorCode.MAX_TURNS:
            # The agent stopped at its own limit with its work and session intact: a stop to report, not a failure.
            self.outcome = _Outcome.TURN_LIMIT
            return []
        self.outcome = _Outcome.FAILED
        message = getattr(error, "message", str(error)) if error else "Unknown error"
        return [{"type": AgentEventType.ERROR.value, "data": message}]


async def stream_direct_delegate(
    pool: DelegationPool,
    agent_name: str,
    prompt: str,
    *,
    session_id: str,
    cancel_token: CancellationToken | None = None,
) -> AsyncGenerator[SseEvent]:
    """Run one turn of ``agent_name`` on ``pool`` and stream it as frontend events.

    Closing the stream (a client that went away) closes the turn, which stops the external process. A tripped
    ``cancel_token`` does the same even while the external agent is silent, and ends the stream with a
    ``CANCELLED`` event.
    """
    config = pool.get_config(agent_name)
    turn = _TurnTranslator(agent_name, config.auth_mode if config else "subscription")
    yield turn.connecting()

    async with (
        aclosing(pool.run_turn(agent_name, prompt, session_id=session_id)) as events,
        on_token_cancelled(cancel_token, lambda: pool.cancel(agent_name, session_id)),
    ):
        async for event in events:
            if cancel_token is not None and cancel_token.is_cancelled:
                await pool.cancel(agent_name, session_id)
                break
            for sse_event in turn.translate(event):
                yield sse_event
            if turn.outcome is _Outcome.CANCELLED:
                break

    if turn.outcome is _Outcome.CANCELLED or (cancel_token is not None and cancel_token.is_cancelled):
        yield {"type": AgentEventType.CANCELLED.value}
        return
    for sse_event in turn.closing():
        yield sse_event
