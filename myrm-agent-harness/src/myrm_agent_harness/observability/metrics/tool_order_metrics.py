"""Tool-call ordering metrics.

[INPUT]
- observability.metrics::create_counter (POS: counter factory that is a no-op without prometheus)

[OUTPUT]
- record_tool_order: count how the conflict gate ordered one tool call against the calls of its model message

[POS]
Makes the ordering of conflicting tool calls observable. ``held_for_order`` counts the calls that reached the gate
before a conflicting call ahead of them in their message and waited for it, the ones arrival order alone would have
run out of the model's order. A rising ``predecessor_absent`` means calls stop reaching the gate within the arrival
grace, and a rising ``turn_unidentified`` means the graph state no longer lets a call be placed in its message; in
both the call is admitted in arrival order. Not a delivery gate.
"""

from __future__ import annotations

from typing import Literal

from myrm_agent_harness.observability.metrics import create_counter

ToolOrderOutcome = Literal["held_for_order", "predecessor_absent", "turn_unidentified"]

tool_call_order_total = create_counter(
    "tool_call_order_total",
    "Tool calls by how the conflict gate ordered them against the calls of their model message",
    ("outcome",),
)


def record_tool_order(outcome: ToolOrderOutcome) -> None:
    """Record one tool call that was held for its predecessors, written off its absent ones, or left unplaced."""
    if tool_call_order_total is not None:
        tool_call_order_total.labels(outcome=outcome).inc()
