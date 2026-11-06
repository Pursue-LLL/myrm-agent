"""Unit tests for CrossTaskRelationConfidenceTierPack (Roadmap Item 26).

Validates the EpisodicMemory schema extensions:
- confidence_tier (strong / weak / shadow)
- relation_category (same_work_item, same_problem, reusable_sop, shadow_context)
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.types import (
    EpisodicMemory,
    MemoryType,
)


def test_episodic_memory_confidence_tier_defaults() -> None:
    ep = EpisodicMemory(content="Standard episodic memory")
    assert ep.memory_type == MemoryType.EPISODIC
    assert ep.confidence_tier == "strong"
    assert ep.relation_category == "same_work_item"


def test_episodic_memory_confidence_tier_assignment() -> None:
    ep = EpisodicMemory(
        content="Historical background context from unrelated work item",
        confidence_tier="shadow",
        relation_category="shadow_context",
    )
    assert ep.confidence_tier == "shadow"
    assert ep.relation_category == "shadow_context"
