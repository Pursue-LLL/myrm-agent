"""The consolidation prompt teaches the model the reply shape that the consolidation models parse.

Structured output in this project is JSON mode: the response schema never reaches the model, so a field the prompt does
not name is a field the model guesses, differently on every call. A guessed reply fails validation as a whole, the
cycle ends with an error and the same oldest memories are sent again. The reply example in the prompt therefore has to
stay a valid ``ConsolidationResponse`` that names every field the models read.

[INPUT]
- strategies.consolidation_prompts::_SYSTEM_PROMPT (POS: the instructions every consolidation call carries)
- strategies.consolidation_models::{ConsolidationAction, ConsolidationResponse, MergeOp, CorrectOp, UpdateContentOp} (POS: the shape a reply is parsed into)

[POS]
Keeps the prompt's reply example and the models that parse the reply in step.
"""

from __future__ import annotations

import re
from typing import TypedDict

import pytest
from pydantic import BaseModel, TypeAdapter

from myrm_agent_harness.toolkits.memory.strategies.consolidation_models import (
    ConsolidationAction,
    ConsolidationResponse,
    CorrectOp,
    MergeOp,
    UpdateContentOp,
)
from myrm_agent_harness.toolkits.memory.strategies.consolidation_prompts import _SYSTEM_PROMPT

_REPLY_EXAMPLE = re.compile(r"```json\n(.*?)\n```", re.DOTALL)

_OPERATION_MODELS: dict[str, type[BaseModel]] = {
    ConsolidationAction.MERGE.value: MergeOp,
    ConsolidationAction.CORRECT.value: CorrectOp,
    ConsolidationAction.UPDATE_CONTENT.value: UpdateContentOp,
}


class _Reply(TypedDict):
    operations: list[dict[str, object]]
    insights: list[str]


def _example() -> _Reply:
    match = _REPLY_EXAMPLE.search(_SYSTEM_PROMPT)
    assert match is not None, "the prompt carries no ```json reply example"
    return TypeAdapter(_Reply).validate_json(match.group(1))


def test_the_example_is_a_reply_the_models_accept() -> None:
    reply = ConsolidationResponse.model_validate(_example())

    assert all(type(op) is _OPERATION_MODELS[op.action] for op in reply.operations)
    assert reply.insights


def test_the_example_shows_every_action_the_models_know() -> None:
    assert {op["action"] for op in _example()["operations"]} == set(_OPERATION_MODELS)
    assert set(_OPERATION_MODELS) == {action.value for action in ConsolidationAction}


@pytest.mark.parametrize("action", list(_OPERATION_MODELS))
def test_an_example_operation_names_only_fields_of_its_model_and_all_the_required_ones(action: str) -> None:
    """Pydantic ignores an unknown key, so a misspelled field in the example would parse and teach the wrong name."""
    model = _OPERATION_MODELS[action]
    operation = next(op for op in _example()["operations"] if op["action"] == action)

    required = {name for name, field in model.model_fields.items() if field.is_required()}
    assert set(operation) <= set(model.model_fields)
    assert required <= set(operation)


@pytest.mark.parametrize("model", [ConsolidationResponse, *_OPERATION_MODELS.values()], ids=lambda m: m.__name__)
def test_the_prompt_names_every_field_the_models_read(model: type[BaseModel]) -> None:
    missing = [name for name in model.model_fields if f'"{name}"' not in _SYSTEM_PROMPT]

    assert not missing, f"{model.__name__} reads fields the prompt never names: {missing}"


def _example_texts() -> list[str]:
    """Every string the example shows, except the ``action`` names."""
    example = _example()
    texts = list(example["insights"])
    for operation in example["operations"]:
        for field, value in operation.items():
            if field == "action":
                continue
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, list):
                texts.extend(item for item in value if isinstance(item, str))
    return texts


def test_every_text_the_example_shows_is_a_placeholder_no_reply_can_copy_as_a_fact() -> None:
    """An insight is stored as a memory as it is: a model that copies a realistic example would plant a false fact."""
    texts = _example_texts()

    assert texts
    assert all(text.startswith("<") and text.endswith(">") for text in texts), texts


def test_a_reply_with_nothing_to_consolidate_is_valid_and_the_prompt_says_how_to_write_it() -> None:
    nothing = '{"operations": [], "insights": []}'

    assert nothing in _SYSTEM_PROMPT
    assert ConsolidationResponse.model_validate_json(nothing) == ConsolidationResponse()
