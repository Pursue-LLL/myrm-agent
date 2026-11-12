"""Apply-time gate of a consolidation operation: is the memory still what the model read?

[INPUT]
- strategies.consolidation_models::is_folded_fragment (POS: marker of a fragment a merge already folded away)
- memory.types::{AnyMemory, MemoryStatus} (POS: memory records and lifecycle status)

[OUTPUT]
- GateRefusal: why an operation may no longer act on a memory
- admit: The memory when the operation may still act on it, otherwise the refusal

[POS]
The model plans every operation against the memories as they were read, and the store moves on while it thinks: the
user archives, edits, pins or deletes a memory, or an earlier cycle folds it into a merged one. The gate re-checks
the store's copy just before the write, so an operation never overwrites a user's edit, restores what the user took
out of play, folds a protected memory away or folds a fragment a second time. A refusal is a skip, not an error.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import is_folded_fragment
from myrm_agent_harness.toolkits.memory.types import MemoryStatus

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import AnyMemory


class GateRefusal(StrEnum):
    MISSING = "missing"
    INACTIVE = "inactive"
    PROTECTED = "protected"
    FOLDED = "folded"
    EDITED = "edited"


def admit(memory: AnyMemory | None, seen_text: str) -> AnyMemory | GateRefusal:
    """The memory itself when an operation planned from ``seen_text`` may still act on it, else why it may not."""
    if memory is None:
        return GateRefusal.MISSING
    if memory.status != MemoryStatus.ACTIVE:
        return GateRefusal.INACTIVE
    if memory.is_user_protected:
        return GateRefusal.PROTECTED
    if is_folded_fragment(memory):
        return GateRefusal.FOLDED
    if memory.content != seen_text:
        return GateRefusal.EDITED
    return memory


__all__ = ["GateRefusal", "admit"]
