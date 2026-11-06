"""Agent profile repository.

[INPUT]
- .store (POS: composed repository)

[OUTPUT]
- AgentRepository

[POS]
Aggregate exit of the agent repository package; import path unchanged.
"""

from __future__ import annotations

from .store import AgentRepository

__all__ = ["AgentRepository"]
