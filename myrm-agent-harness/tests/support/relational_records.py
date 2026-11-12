"""Record builders of the relational store tests.

[INPUT]
- toolkits.memory.types::MemoryType, PendingRecord, ProceduralMemory (POS: Memory type definitions)

[OUTPUT]
- make_rule: an active procedural rule for a trigger and an action
- make_pending: a pending semantic-memory record with the given content

[POS]
Harness pytest-only record builders shared by the relational store tests, so a test states the record it needs
and not its constructor.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.types import MemoryType, PendingRecord, ProceduralMemory


def make_rule(trigger: str = "user asks", action: str = "respond") -> ProceduralMemory:
    return ProceduralMemory(
        content=f"When: {trigger} → Do: {action}",
        trigger=trigger,
        action=action,
    )


def make_pending(content: str = "test memory") -> PendingRecord:
    return PendingRecord(memory_type=MemoryType.SEMANTIC, content=content)
