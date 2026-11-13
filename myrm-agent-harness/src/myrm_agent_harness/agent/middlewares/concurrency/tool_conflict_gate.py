"""Which tool calls of one agent may run at the same moment, and in what order those that conflict start.

[INPUT]
- agent.security.tool_registry::resolve_safety_metadata (POS: tool safety metadata, fail-closed for undeclared tools)
- concurrency.conflict_gate::ConflictGate (POS: shared / exclusive admission in arrival order)
- concurrency.turn_ledger::TurnLedger (POS: the calls of one model message that are still on their way to the gate)
- observability.metrics.tool_order_metrics::record_tool_order (POS: counts how a call was ordered)
- langchain.agents.middleware::AgentMiddleware (POS: tool-call middleware base)

[OUTPUT]
- ToolConflictGateMiddleware: runs concurrency-safe calls together and every other call alone, and starts the calls of
  one model message that conflict in the order the model made them

[POS]
The calls of one model message reach the tool node as separate tasks that reach this middleware in no fixed order.
A call that is concurrency-safe takes a shared hold; any other call, including a tool nobody declared, takes an
exclusive one, so it never overlaps any other call of the agent. Two calls of one message conflict when at least one
of them is not concurrency-safe. The gate admits in arrival order, so a call first waits until the conflicting calls
ahead of it in its message have reached the gate, which takes the event loop a few turns, and only then joins the
line: conflicting calls start in the model's order and concurrency-safe calls still run together. A call that does
not reach the gate within the arrival grace is not waited for any longer, and a call that cannot be placed in its
message is admitted in arrival order. One call failing never changes what another does: each call answers with its
own result. The gate sits outside ``tool_interceptor_middleware`` so a call's timeout does not run down while it
waits.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware, AgentState, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from myrm_agent_harness.agent.middlewares.concurrency.conflict_gate import ConflictGate
from myrm_agent_harness.agent.middlewares.concurrency.turn_ledger import CallTurn, NoTurn, TurnLedger
from myrm_agent_harness.agent.security.tool_registry import resolve_safety_metadata
from myrm_agent_harness.observability.metrics.tool_order_metrics import record_tool_order

logger = logging.getLogger(__name__)

# A call reaches the gate a few event-loop turns after its message is dispatched. A loop that stalls for longer is
# already critical to the gateway health probe, and ordering is then the least of what goes wrong.
ARRIVAL_GRACE_SECONDS = 1.0


class ToolConflictGateMiddleware(AgentMiddleware[AgentState[object], None, object]):
    """Admit each tool call through a gate that keeps every call that is not concurrency-safe alone."""

    def __init__(self, arrival_grace_seconds: float = ARRIVAL_GRACE_SECONDS) -> None:
        super().__init__()
        self._gate = ConflictGate()
        self._turns = TurnLedger()
        self._arrival_grace_seconds = arrival_grace_seconds

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[object]]],
    ) -> ToolMessage | Command[object]:
        call_id = request.tool_call["id"] or ""
        exclusive = not resolve_safety_metadata(request.tool_call["name"]).is_concurrent_safe
        turn = self._turns.turn_of(request.state, call_id)
        if isinstance(turn, NoTurn):
            if turn is NoTurn.UNIDENTIFIED:
                record_tool_order("turn_unidentified")
            async with self._gate.hold(exclusive=exclusive):
                return await handler(request)
        try:
            ahead = turn.unarrived_ahead_of(call_id, exclusive=exclusive)
            if ahead:
                record_tool_order("held_for_order")
                await self._wait_until_arrived(turn, ahead)
            # Nothing may suspend between announcing the arrival and joining the line: a call that this releases
            # takes its place behind this one.
            turn.mark_arrived(call_id)
            async with self._gate.hold(exclusive=exclusive):
                return await handler(request)
        finally:
            # A call that stops waiting for its predecessors (cancelled) still counts as arrived for the ones behind it.
            turn.mark_arrived(call_id)

    async def _wait_until_arrived(self, turn: CallTurn, call_ids: list[str]) -> None:
        try:
            async with asyncio.timeout(self._arrival_grace_seconds):
                await turn.wait_until_arrived(call_ids)
        except TimeoutError:
            absent = turn.write_off(call_ids)
            if absent:
                record_tool_order("predecessor_absent")
                logger.warning(
                    "Tool calls %s did not reach the conflict gate within %.1fs; calls behind them no longer wait",
                    absent,
                    self._arrival_grace_seconds,
                )
