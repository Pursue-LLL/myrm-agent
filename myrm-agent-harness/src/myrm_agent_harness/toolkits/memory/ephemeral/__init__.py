"""Ephemeral and read-only memory managers for subagent isolation.

Provides two isolation strategies:
- EphemeralMemoryManager: reads from parent, writes to a local dict (no DB pollution).
- ReadOnlyMemoryView: reads from parent, all writes raise PermissionError.

[INPUT]
- ephemeral.dict_backed::EphemeralMemoryManager (POS: dict-backed strategy)
- ephemeral.read_only_view::ReadOnlyMemoryView (POS: read-only strategy)

[OUTPUT]
- ReadOnlyMemoryView: Read-only proxy over a parent MemoryManager.
- EphemeralMemoryManager: Dict-backed ephemeral memory manager.

[POS]
Facade of the subagent memory isolation strategies.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.ephemeral.dict_backed import EphemeralMemoryManager
from myrm_agent_harness.toolkits.memory.ephemeral.read_only_view import ReadOnlyMemoryView

__all__ = ["EphemeralMemoryManager", "ReadOnlyMemoryView"]
