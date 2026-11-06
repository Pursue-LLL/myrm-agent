"""Unit tests for SubtaskPhaseTaggedEpisodicMemoryPack.

Validates the EpisodicMemory schema enhancements (subtask_phase, is_failure_attempt, failure_reason, negative_lesson).
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, MemoryType


def test_episodic_memory_subtask_phase_fields_default() -> None:
    ep = EpisodicMemory(content="Analyzed memory context")
    assert ep.memory_type == MemoryType.EPISODIC
    assert ep.subtask_phase is None
    assert ep.is_failure_attempt is False
    assert ep.failure_reason is None
    assert ep.negative_lesson is None


def test_episodic_memory_subtask_phase_failure_fields() -> None:
    ep = EpisodicMemory(
        content="Attempted to use sync sqlite in async loop",
        subtask_phase="edit",
        is_failure_attempt=True,
        failure_reason="BlockingIOError: cannot run synchronous connection in async event loop",
        negative_lesson="Always use aiosqlite or run_in_executor for SQLite access in async services",
    )
    assert ep.subtask_phase == "edit"
    assert ep.is_failure_attempt is True
    assert "BlockingIOError" in (ep.failure_reason or "")
    assert "Always use aiosqlite" in (ep.negative_lesson or "")
