# concurrency/

## Overview

Concurrency controls — subagent semaphore limits, and the gate that keeps the tool calls of one agent that are
not concurrency-safe from overlapping any other call.

Detailed design: [MIDDLEWARE_SYSTEM.md](../MIDDLEWARE_SYSTEM.md)

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Public exports for the concurrency limiter and the tool conflict gate. | — |
| `concurrency_limiter.py` | Core | Subagent Semaphore by agent_type; `get_subagent_semaphore` accessor. | ✅ |
| `conflict_gate.py` | Core | `ConflictGate`: shared holders run together, an exclusive holder runs alone, admission in arrival order, cancellation-safe. | ✅ |
| `tool_conflict_gate.py` | Core | `ToolConflictGateMiddleware`: concurrency-safe calls take a shared hold, every other call (undeclared tools and host-serial MCP tools included) an exclusive one; later exclusive calls of a model turn whose earlier exclusive call failed are answered as skipped. | ✅ |

## Key Dependencies

- `agent.security.tool_registry` — SafetyMetadata, resolve_safety_metadata
- `langchain.agents.middleware` — AgentMiddleware base
