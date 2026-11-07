"""memory_save_tool offers the model what its write policy allows, measured on the schema the provider receives."""

from __future__ import annotations

import inspect
from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import BaseTool, StructuredTool

from myrm_agent_harness.toolkits.llms.adapters.chat_model.binding import tool_bind_kwargs
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.save_tool import (
    MemorySaveInput,
    build_memory_save_tool,
    memory_save_input,
)
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchPolicy

_SHARED_WRITE = MemorySearchPolicy()
_BOUND_ONLY = MemorySearchPolicy(allow_shared_write=False)

_POLICIES = [
    pytest.param(_SHARED_WRITE, id="shared-write"),
    pytest.param(_BOUND_ONLY, id="bound-only"),
]

# Argument shapes recorded from real model traffic against memory_save_tool (values shortened).
_RECORDED_CALLS = [
    {"content": "Manager Dana dislikes long emails.", "category": "knowledge", "importance": 0.7, "tags": ["email"]},
    {"content": "Timezone is UTC+8.", "category": "knowledge", "importance": 0.9, "write_target": "shared"},
    {"content": "Always reply in Chinese.", "category": "instruction", "importance": 0.95, "write_target": "shared"},
    {
        "content": "Dana prefers short emails.",
        "category": "preference",
        "importance": 0.8,
        "preference_key": "manager_email_format",
        "write_target": "shared",
    },
    {
        "content": "Production database writes are frozen every Friday.",
        "category": "rule",
        "importance": 0.9,
        "rule_trigger": "when changing the production database",
        "write_target": "shared",
    },
]


def _build(policy: MemorySearchPolicy) -> BaseTool:
    return build_memory_save_tool(MagicMock(), policy, description="d")


def _wire_properties(policy: MemorySearchPolicy) -> dict[str, dict[str, object]]:
    """The ``properties`` of memory_save_tool exactly as ``tool_bind_kwargs`` hands them to the provider."""
    bound = tool_bind_kwargs(
        [_build(policy)],
        model_id="gpt-5",
        api_base="",
        custom_llm_provider="openai",
        tool_choice=None,
        parallel_tool_calls=None,
        extra={},
    )
    wire_tool = cast(list[dict[str, dict[str, dict[str, dict[str, dict[str, object]]]]]], bound["tools"])[0]
    return wire_tool["function"]["parameters"]["properties"]


@pytest.mark.parametrize("policy", _POLICIES)
def test_write_target_is_offered_only_while_shared_writes_are_allowed(policy: MemorySearchPolicy) -> None:
    write_target = _wire_properties(policy).get("write_target")
    if policy.allow_shared_write:
        assert write_target is not None
        assert write_target["enum"] == ["bound", "shared"]
    else:
        assert write_target is None


def test_blocking_shared_writes_removes_no_other_argument() -> None:
    assert set(_wire_properties(_SHARED_WRITE)) - {"write_target"} == set(_wire_properties(_BOUND_ONLY))


def test_the_blocked_schema_differs_from_the_default_only_by_write_target() -> None:
    """Whatever else the raw schema carries reaches a provider that reads it (a class docstring becomes its description)."""
    default, blocked = (memory_save_input(policy).model_json_schema() for policy in (_SHARED_WRITE, _BOUND_ONLY))
    for schema in (default, blocked):
        schema.pop("title")
    default["properties"].pop("write_target")
    assert blocked == default


@pytest.mark.parametrize("policy", _POLICIES)
def test_recorded_call_shapes_stay_valid(policy: MemorySearchPolicy) -> None:
    schema = memory_save_input(policy)
    for arguments in _RECORDED_CALLS:
        schema.model_validate(arguments)


def test_a_blocked_policy_still_accepts_shared_so_the_tool_can_demote_it() -> None:
    """A blocked policy does not offer ``write_target``, yet a caller that sends it still reaches the demotion."""
    schema = memory_save_input(_BOUND_ONLY)
    assert schema.model_validate({"content": "x", "write_target": "shared"}).write_target == "shared"
    assert schema.model_validate({"content": "x"}).write_target == "bound"


def test_save_policies_that_differ_only_in_corpus_access_share_one_schema_class() -> None:
    wiki = MemorySearchPolicy(allow_wiki=True, allow_shared_write=False)
    sessions = MemorySearchPolicy(allow_sessions=True, allow_shared_write=False)
    assert memory_save_input(wiki) is memory_save_input(sessions)
    assert memory_save_input(MemorySearchPolicy(allow_wiki=True)) is MemorySaveInput


def test_coroutine_accepts_every_argument_the_widest_schema_offers() -> None:
    """The schema narrows what is offered; the coroutine behind it must still take everything any policy offers."""
    tool = cast(StructuredTool, _build(_BOUND_ONLY))
    assert tool.coroutine is not None
    assert set(inspect.signature(tool.coroutine).parameters) == set(MemorySaveInput.model_fields)
