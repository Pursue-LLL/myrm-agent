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
so it never overlaps any other call of the agent. The contract is mutual exclusion, not call order, and one call
failing never changes what another does: each call answers with its own result. The gate sits outside
``tool_interceptor_middleware`` so a call's timeout does not run down while it waits.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares.concurrency.conflict_gate import ConflictGate
from myrm_agent_harness.agent.security.tool_registry import resolve_safety_metadata


class ToolConflictGateMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Admit each tool call through a gate that keeps every call that is not concurrency-safe alone."""

    def __init__(self) -> None:
        super().__init__()
        self._gate = ConflictGate()

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        exclusive = not resolve_safety_metadata(request.tool_call["name"]).is_concurrent_safe
        async with self._gate.hold(exclusive=exclusive):
            return await handler(request)
