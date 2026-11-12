"""Consolidation models bound what an LLM returns before it reaches storage, and mark what a merge folded."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    CONSOLIDATED_FLAG_KEY,
    ConsolidationResponse,
    UpdateContentOp,
    is_folded_fragment,
)
from myrm_agent_harness.toolkits.memory.types import SemanticMemory


@pytest.mark.parametrize("importance", [None, 0.0, 0.5, 1.0])
def test_a_content_update_accepts_an_importance_inside_the_unit_range(importance: float | None) -> None:
    assert UpdateContentOp(memory_id="m1", new_content="text", importance=importance).importance == importance


@pytest.mark.parametrize("importance", [-0.1, 1.1, 8.0])
def test_a_content_update_rejects_an_importance_outside_the_unit_range(importance: float) -> None:
    with pytest.raises(ValidationError):
        UpdateContentOp(memory_id="m1", new_content="text", importance=importance)


def test_one_out_of_range_operation_rejects_the_whole_response() -> None:
    good = {"action": "update_content", "memory_id": "m1", "new_content": "text", "importance": 0.4}
    bad = {**good, "memory_id": "m2", "importance": 8}

    with pytest.raises(ValidationError):
        ConsolidationResponse.model_validate({"operations": [good, bad], "insights": []})


def test_a_memory_is_a_folded_fragment_only_once_a_merge_flagged_it() -> None:
    assert is_folded_fragment(SemanticMemory(content="x", metadata={CONSOLIDATED_FLAG_KEY: True}))
    assert not is_folded_fragment(SemanticMemory(content="x", metadata={CONSOLIDATED_FLAG_KEY: False}))
    assert not is_folded_fragment(SemanticMemory(content="x"))
