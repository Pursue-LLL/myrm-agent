"""memory_search_tool offers the model what its corpus policy allows, measured on the schema the provider receives."""

from __future__ import annotations

import inspect
from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import ValidationError

from myrm_agent_harness.toolkits.llms.adapters.chat_model.binding import tool_bind_kwargs
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.search_input import memory_search_input
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.search_tool import build_memory_search_tool
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchBackends,
    MemorySearchPolicy,
    advertised_search_corpora,
)

_WIDEST = MemorySearchPolicy(allow_wiki=True, allow_sessions=True)
_EXPAND_FIELDS = {"expand_conversation_id", "expand_message_id", "expand_window"}
_COMMON_FIELDS = {
    "query",
    "categories",
    "limit",
    "profile_key",
    "memory_id",
    "detail_level",
    "domain",
    "since",
    "until",
}

_POLICIES = [
    pytest.param(MemorySearchPolicy(), id="memory-only"),
    pytest.param(MemorySearchPolicy(allow_wiki=True), id="wiki"),
    pytest.param(MemorySearchPolicy(allow_sessions=True), id="sessions"),
    pytest.param(_WIDEST, id="wiki-and-sessions"),
]

# Argument sets recorded from real agent traffic against memory_search_tool.
_RECORDED_CALLS = [
    {"query": "x"},
    {"query": "x", "limit": 5},
    {"query": "x", "corpus": "memory"},
    {"query": "x", "corpus": "all", "limit": 5},
    {"query": "x", "categories": ["knowledge"], "limit": 5},
    {"query": "x", "categories": ["knowledge"], "corpus": "memory"},
    {"query": "x", "corpus": "memory", "detail_level": "full", "limit": 5},
    {"query": "x", "corpus": "memory", "limit": 5, "since": "2026-01-01"},
]


def _build(policy: MemorySearchPolicy) -> BaseTool:
    return build_memory_search_tool(MagicMock(), policy, MemorySearchBackends(), description="d")


def _wire_properties(policy: MemorySearchPolicy) -> dict[str, dict[str, object]]:
    """The ``properties`` of memory_search_tool exactly as ``tool_bind_kwargs`` hands them to the provider."""
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
def test_offered_corpus_values_are_the_advertised_ones(policy: MemorySearchPolicy) -> None:
    advertised = advertised_search_corpora(policy)
    corpus = _wire_properties(policy).get("corpus")
    if len(advertised) == 1:
        assert corpus is None
    else:
        assert corpus is not None
        assert corpus["enum"] == list(advertised)


@pytest.mark.parametrize("policy", _POLICIES)
def test_conversation_expansion_is_offered_only_with_sessions(policy: MemorySearchPolicy) -> None:
    expand = {name for name in _wire_properties(policy) if name.startswith("expand_")}
    assert expand == (_EXPAND_FIELDS if policy.allow_sessions else set())


@pytest.mark.parametrize("policy", _POLICIES)
def test_every_policy_keeps_the_common_arguments(policy: MemorySearchPolicy) -> None:
    assert set(_wire_properties(policy)) >= _COMMON_FIELDS


@pytest.mark.parametrize("policy", _POLICIES)
def test_recorded_call_shapes_stay_valid(policy: MemorySearchPolicy) -> None:
    schema = memory_search_input(policy)
    for arguments in _RECORDED_CALLS:
        schema.model_validate(arguments)


@pytest.mark.parametrize(
    ("corpus", "refusal"),
    [
        ("sessions", "Conversation history search is disabled. Enable it in Memory settings."),
        ("wiki", "Wiki search is not enabled for this agent."),
    ],
)
async def test_memory_only_refuses_a_stray_corpus_instead_of_searching_memory(corpus: str, refusal: str) -> None:
    """``corpus`` is no longer advertised under a memory-only policy, but a caller that sends it must be told no."""
    assert await _build(MemorySearchPolicy()).ainvoke({"query": "q", "corpus": corpus}) == refusal


async def test_a_corpus_outside_the_offered_enum_is_a_validation_error() -> None:
    with pytest.raises(ValidationError, match="memory"):
        await _build(MemorySearchPolicy(allow_wiki=True)).ainvoke({"query": "q", "corpus": "sessions"})


def test_search_policies_that_differ_only_in_write_access_share_one_schema_class() -> None:
    read_only = MemorySearchPolicy(allow_wiki=True, allow_shared_write=False)
    assert memory_search_input(MemorySearchPolicy(allow_wiki=True)) is memory_search_input(read_only)


def test_coroutine_accepts_every_argument_the_widest_schema_offers() -> None:
    """The schema narrows what is offered; the coroutine behind it must still take everything any policy offers."""
    tool = cast(StructuredTool, _build(_WIDEST))
    assert tool.coroutine is not None
    assert set(inspect.signature(tool.coroutine).parameters) == set(memory_search_input(_WIDEST).model_fields)
