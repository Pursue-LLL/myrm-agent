"""Agent execution stream event types.

[INPUT]
- channels.types.components::QuickReply (POS: UI component types)

[OUTPUT]
- ProgressUpdate, StreamingText: placeholder-edit transport events
- ApprovalExpiry: how long a tool approval waits and what the timeout decides
- METADATA_APPROVAL_WINDOW_SECONDS_KEY: ``InboundMessage.metadata`` key that sets a turn's approval wait
- METADATA_RESUME_SESSION_KEY: ``InboundMessage.metadata`` key naming the channel session a resume turn continues
- FissionTopologyNode, FissionTopologyUpdate: swarm fission topology events

[POS]
Events yielded by AgentExecutor.execute_stream() and consumed by AgentRouter;
zero I/O, pure data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .components import QuickReply

METADATA_APPROVAL_WINDOW_SECONDS_KEY = "approval_window_seconds"
# The channel session key of the turn that asked for a tool approval: the run it resumes goes back to that session.
METADATA_RESUME_SESSION_KEY = "resume_session_key"


@dataclass(frozen=True, slots=True)
class ApprovalExpiry:
    """How long a tool approval waits for an answer and the decision its timeout applies."""

    seconds: float
    behavior: Literal["deny", "allow"] = "deny"


@dataclass(frozen=True, slots=True)
class ProgressUpdate:
    """A human-readable progress label emitted during Agent execution.

    Yielded by AgentExecutor.execute_stream() between tool calls.
    Consumed by AgentRouter to edit Placeholder messages in real-time.

    When ``quick_replies`` is non-empty, the Router sends them alongside
    the progress text — enabling interactive prompts like tool approval
    buttons in IM channels. ``expiry`` is set on such a prompt when the wait has a
    time limit; the Router then owns the timer that ends it. ``session_key`` is set on it
    too: the channel session the asking run belongs to, which the Router keeps with the open
    request so the answer resumes that session's chat however the reset policy has moved on.
    """

    label: str
    quick_replies: tuple[QuickReply, ...] = ()
    expiry: ApprovalExpiry | None = None
    session_key: str = ""


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
