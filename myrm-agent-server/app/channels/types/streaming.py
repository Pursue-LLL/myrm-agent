"""Agent execution stream event types.

[INPUT]
- channels.types.components::QuickReply (POS: UI component types)

[OUTPUT]
- ProgressUpdate, StreamingText: placeholder-edit transport events
- FissionTopologyNode, FissionTopologyUpdate: swarm fission topology events

[POS]
Events yielded by AgentExecutor.execute_stream() and consumed by AgentRouter;
zero I/O, pure data.
"""

from __future__ import annotations

from dataclasses import dataclass

from .components import QuickReply


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """A human-readable progress label emitted during Agent execution.

    Yielded by AgentExecutor.execute_stream() between tool calls.
    Consumed by AgentRouter to edit Placeholder messages in real-time.

    When ``quick_replies`` is non-empty, the Router sends them alongside
    the progress text — enabling interactive prompts like tool approval
    buttons in IM channels.
    """

    label: str
    quick_replies: tuple[QuickReply, ...] = ()


@dataclass(frozen=True, slots=True)
class FissionTopologyNode:
    """Represents a single subagent node in a Fission topology map."""

    node_id: str
    agent_type: str
    objective: str
    status: str  # "pending", "running", "completed", "failed", "paused"
    error: str | None = None
    cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class FissionTopologyUpdate:
    """A structured update for a Swarm Fission topology map.

    Yielded by AgentExecutor.execute_stream() when subagents spawn, update status, or complete.
    Consumed by Frontend GUI to render a React Flow DAG representing the parallel task execution.
    """

    fission_id: str
    nodes: tuple[FissionTopologyNode, ...]
    total_cost_usd: float = 0.0


@dataclass(frozen=True, slots=True)
class StreamingText:
    """Accumulated streaming text snapshot emitted during answer generation.

    Yielded by AgentExecutor.execute_stream() as the LLM generates tokens.
    Consumed by AgentRouter to progressively edit Placeholder messages,
    giving users real-time visibility into the response being generated.
    The ``text`` field contains the full accumulated text (not a delta).
    """

    text: str
