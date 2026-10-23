"""Persistent Agent Session Multiplexer public API.

[INPUT]
- types::(
    AgentInstruction, InspectSnapshot, InstructResult, MultiplexerSession, MultiplexerSessionState
  )
- session_multiplexer::(AgentSessionMultiplexer, get_session_multiplexer)

[OUTPUT]
- __all__: Exported public symbols for agent multiplexing and cross-agent coordination.

[POS]
Harness sub-package facade for tmux-style agent session multiplexing.
"""

from __future__ import annotations

from myrm_agent_harness.agent.sub_agents.multiplexer.session_multiplexer import (
    AgentSessionMultiplexer,
    get_session_multiplexer,
)
from myrm_agent_harness.agent.sub_agents.multiplexer.types import (
    AgentInstruction,
    InspectSnapshot,
    InstructResult,
    MultiplexerSession,
    MultiplexerSessionState,
)

__all__ = [
    "AgentInstruction",
    "AgentSessionMultiplexer",
    "InspectSnapshot",
    "InstructResult",
    "MultiplexerSession",
    "MultiplexerSessionState",
    "get_session_multiplexer",
]
