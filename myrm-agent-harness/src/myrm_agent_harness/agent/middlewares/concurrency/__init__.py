"""Concurrency subsystem — the gate that keeps conflicting tool calls apart.

[INPUT]
- langchain.agents.middleware (AgentMiddleware base)
- agent.security.tool_registry (resolve_safety_metadata: which tools are concurrency-safe)

[OUTPUT]
- ToolConflictGateMiddleware: keeps every call that is not concurrency-safe alone
"""

from myrm_agent_harness.agent.middlewares.concurrency.tool_conflict_gate import (
    ToolConflictGateMiddleware,
)

__all__ = [
    "ToolConflictGateMiddleware",
]
