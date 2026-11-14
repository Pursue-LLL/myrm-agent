# concurrency/

## Overview

Concurrency control — the gate that keeps the tool calls of one agent that are not concurrency-safe from
overlapping any other call, and starts the calls of one model message that conflict in the order the model made them.

Detailed design: [MIDDLEWARE_SYSTEM.md](../MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public export for the tool conflict gate. | — |
| `conflict_gate.py` | Core | `ConflictGate`: shared holders run together, an exclusive holder runs alone, admission in arrival order (a holder takes its place the moment it enters), cancellation-safe. | ✅ |
| `turn_ledger.py` | Core | `TurnLedger`, `CallTurn`, `NoTurn`: the calls of one model message that have no answer yet, in the model's order, read from the graph state when its first call is dispatched; each call has an arrival signal. | ✅ |
| `tool_conflict_gate.py` | Core | `ToolConflictGateMiddleware`: concurrency-safe calls take a shared hold, every other call (undeclared tools and host-serial MCP tools included) an exclusive one; a call first waits for the conflicting calls ahead of it in its message to reach the gate (arrival, not completion; written off after the arrival grace), so conflicting calls start in the model's order; one call failing never changes what another does. | ✅ |

## Key Dependencies

- `agent.security.tool_registry` — SafetyMetadata, resolve_safety_metadata
- `observability.metrics.tool_order_metrics` — `tool_call_order_total` (held for order / predecessor absent / turn unidentified)
- `langchain.agents.middleware` — AgentMiddleware base
