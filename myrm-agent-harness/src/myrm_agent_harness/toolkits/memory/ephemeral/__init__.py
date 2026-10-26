"""Read-only memory view for subagent isolation.

[INPUT]
- ephemeral.read_only_view::ReadOnlyMemoryView (POS: the one isolation strategy)

[OUTPUT]
- ReadOnlyMemoryView: Read-only proxy over a parent MemoryManager.

[POS]
Facade of the subagent memory isolation.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.ephemeral.read_only_view import ReadOnlyMemoryView

__all__ = ["ReadOnlyMemoryView"]
