"""Consolidation response models bound the numbers an LLM returns before any of them reaches storage."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import ConsolidationResponse, UpdateContentOp


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
