"""Protection and exact-fact state exposed by the memory DTO projection."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.memory import MemoryType
from myrm_agent_harness.toolkits.memory.types import EpisodicMemory, ProceduralMemory, SemanticMemory

from app.services.memory.operations.presentation import memory_to_item


@pytest.mark.parametrize(
    ("mem_type", "memory_cls"),
    [(MemoryType.SEMANTIC, SemanticMemory), (MemoryType.EPISODIC, EpisodicMemory)],
)
def test_pinned_vector_memory_is_reported_as_user_locked(mem_type, memory_cls):
    item = memory_to_item(memory_cls(content="prefers concise answers", pinned=True), mem_type)

    assert item.is_user_locked is True


@pytest.mark.parametrize(
    ("mem_type", "memory_cls"),
    [(MemoryType.SEMANTIC, SemanticMemory), (MemoryType.EPISODIC, EpisodicMemory)],
)
def test_unpinned_vector_memory_reports_no_lock(mem_type, memory_cls):
    item = memory_to_item(memory_cls(content="prefers concise answers"), mem_type)

    assert not item.is_user_locked


def test_locked_rule_is_still_reported_as_user_locked():
    rule = ProceduralMemory(content="rule", trigger="when asked", action="answer briefly", is_user_locked=True)

    assert memory_to_item(rule, MemoryType.PROCEDURAL).is_user_locked is True


def test_exact_fact_state_is_projected_from_the_typed_fields():
    memory = SemanticMemory(content="server at 10.0.0.5:8080", is_exact_fact=True, exact_identifiers=["10.0.0.5:8080"])

    item = memory_to_item(memory, MemoryType.SEMANTIC)

    assert item.is_exact_fact is True
    assert item.exact_identifiers == ["10.0.0.5:8080"]


def test_metadata_does_not_stand_in_for_the_typed_exact_fact_state():
    item = memory_to_item(SemanticMemory(content="note", metadata={"is_exact_fact": True}), MemoryType.SEMANTIC)

    assert item.is_exact_fact is False
    assert item.exact_identifiers == []
