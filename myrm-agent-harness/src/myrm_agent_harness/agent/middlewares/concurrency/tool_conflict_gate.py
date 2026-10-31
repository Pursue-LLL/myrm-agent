"""Which tool calls of one agent may run at the same moment.

[INPUT]
- agent.security.tool_registry::resolve_safety_metadata (POS: tool safety metadata, fail-closed for undeclared tools)
- concurrency.conflict_gate::ConflictGate (POS: shared / exclusive admission in arrival order)
- langchain.agents.middleware::AgentMiddleware (POS: tool-call middleware base)

[OUTPUT]
- ToolConflictGateMiddleware: runs concurrency-safe calls together and every other call alone

[POS]
The calls of one model turn reach the tool node as separate tasks that start in no fixed order. A call that is
concurrency-safe takes a shared hold; any other call, including a tool nobody declared, takes an exclusive one,
so it never overlaps any other call of the agent. The contract is mutual exclusion, not call order. Once an
exclusive call of a model turn has failed, the turn's later exclusive calls are answered as skipped. The gate
sits outside ``tool_interceptor_middleware`` so a call's timeout does not run down while it waits.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping

from langchain.agents.middleware import AgentMiddleware, AgentState, ToolCallRequest
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares.concurrency.conflict_gate import ConflictGate
from myrm_agent_harness.agent.security.tool_registry import resolve_safety_metadata
from myrm_agent_harness.utils.logger_utils import get_agent_logger

logger = get_agent_logger(__name__)

_SKIPPED_NOTICE = (
    "[SKIPPED] This tool was skipped because a previous tool in the same batch failed. "
    "The partial results of the successful tools have been preserved."
)

# A turn's calls all arrive within one run step, so only the latest turns can still have calls to skip.
_REMEMBERED_FAILED_TURNS = 128


def _messages_of(state: object) -> list[object]:
    if isinstance(state, Mapping):
        messages = state.get("messages", [])
    elif isinstance(state, list):
        messages = state
    else:
        messages = getattr(state, "messages", [])
    return messages if isinstance(messages, list) else []


def _turn_id(request: ToolCallRequest) -> str | None:
    """The id of the model message that made this call; the calls of one turn share it."""
    call_id = request.tool_call.get("id")
    if not call_id:
        return None
    for message in reversed(_messages_of(request.state)):
        if isinstance(message, AIMessage) and any(call.get("id") == call_id for call in message.tool_calls):
            return message.id
    return None


class ToolConflictGateMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Admit each tool call through a gate that keeps every call that is not concurrency-safe alone."""

    def __init__(self) -> None:
        super().__init__()
        self._gate = ConflictGate()
        self._failed_turns: OrderedDict[str, None] = OrderedDict()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        tool_name = request.tool_call["name"]
        if resolve_safety_metadata(tool_name).is_concurrent_safe:
            async with self._gate.hold(exclusive=False):
                return await handler(request)

        turn_id = _turn_id(request)
        async with self._gate.hold(exclusive=True):
            if turn_id in self._failed_turns:
                logger.warning("Skipping %s: an earlier tool call of the same model turn failed", tool_name)
                return ToolMessage(
                    content=_SKIPPED_NOTICE,
                    name=tool_name,
                    tool_call_id=request.tool_call["id"] or "",
                    status="error",
                )
            result = await handler(request)
            if turn_id is not None and isinstance(result, ToolMessage) and result.status == "error":
                self._remember_failed(turn_id)
            return result

    def _remember_failed(self, turn_id: str) -> None:
        self._failed_turns[turn_id] = None
        if len(self._failed_turns) > _REMEMBERED_FAILED_TURNS:
            self._failed_turns.popitem(last=False)
