"""What the memory tool descriptions say about the tools' own surface is true under the active policy.

A description is prompt text the model acts on: naming an argument, tool or corpus it cannot use sends it into a dead
end. The matrix builds the real tools for every corpus policy, write policy, locale and approval mode and holds each
description against the schemas the provider receives (the MCP surface against the MCP server's own tool schemas).
"""

from __future__ import annotations

import itertools
import re
from dataclasses import replace
from typing import cast
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model.binding import tool_bind_kwargs
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server.server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.factory import create_memory_tools
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchPolicy

_IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
# "field=value" is how a description tells the model which value of an enumerated argument to pass.
_FIELD_VALUE = re.compile(r"\b([a-z_]+)=([a-z_]+)\b")
_GUIDE_ENTRY = re.compile(r"^- ([a-z]+)[:：]", re.MULTILINE)
_WIKI = re.compile("wiki", re.IGNORECASE)
# The word "sessions" also means plain chat sessions in prose, so conversation search is recognised by what only it has.
_SESSIONS_SEARCH = re.compile(r"corpus=sessions|expand_\w+|\bmessage_id\b|^- sessions[:：]", re.MULTILINE)
_AGENT_TOOL_NAMES = {"memory_search_tool", "memory_save_tool", "memory_manage_tool", "wiki_ingest_tool"}
# A field of the sessions hit the model reads, not an argument it passes.
_RESULT_FIELDS = {"message_id"}
# Every argument memory_save_tool can send to the provider is read by the save path; one nothing reads is text without
# a reader. write_target goes out only while the policy allows shared writes.
_SAVE_ARGUMENTS = {
    "content",
    "category",
    "importance",
    "tags",
    "write_target",
    "preference_key",
    "rule_trigger",
    "rule_priority",
}

_CORPUS_POLICIES = {
    "memory-only": MemorySearchPolicy(),
    "wiki": MemorySearchPolicy(allow_wiki=True),
    "sessions": MemorySearchPolicy(allow_sessions=True),
    "wiki-and-sessions": MemorySearchPolicy(allow_wiki=True, allow_sessions=True),
}
_WRITE_POLICIES = {"shared-write": True, "bound-only": False}
_MATRIX = [
    pytest.param(
        replace(corpus_policy, allow_shared_write=allow_shared_write),
        locale,
        approval,
        id=f"{corpus_id}-{write_id}-{locale}-{'approval' if approval else 'direct'}",
    )
    for (corpus_id, corpus_policy), (write_id, allow_shared_write), locale, approval in itertools.product(
        _CORPUS_POLICIES.items(), _WRITE_POLICIES.items(), ("en", "zh"), (False, True)
    )
]

type WireFunction = dict[str, object]


def _wire_functions(policy: MemorySearchPolicy, locale: str, approval_required: bool) -> dict[str, WireFunction]:
    """The memory tools as ``tool_bind_kwargs`` hands them to the provider, by tool name."""
    manager = MagicMock()
    manager.approval_required = approval_required
    tools = create_memory_tools(manager, search_policy=policy, description_locale=locale)
    bound = tool_bind_kwargs(
        tools,
        model_id="gpt-5",
        api_base="",
        custom_llm_provider="openai",
        tool_choice=None,
        parallel_tool_calls=None,
        extra={},
    )
    wire_tools = cast(list[dict[str, WireFunction]], bound["tools"])
    return {str(wire_tool["function"]["name"]): wire_tool["function"] for wire_tool in wire_tools}


def _fields(function: WireFunction) -> set[str]:
    parameters = cast(dict[str, dict[str, object]], function["parameters"])
    return set(parameters["properties"])


def _enum_values(function: WireFunction) -> dict[str, set[str]]:
    """Each enumerated argument of one tool, with the values the schema accepts for it."""
    parameters = cast(dict[str, dict[str, dict[str, object]]], function["parameters"])
    return {
        field: set(cast(list[str], schema["enum"]))
        for field, schema in parameters["properties"].items()
        if "enum" in schema
    }


def _description(function: WireFunction) -> str:
    return str(function["description"])


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_descriptions_name_only_arguments_and_tools_that_exist(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    functions = _wire_functions(policy, locale, approval)
    every_field = set().union(*(_fields(function) for function in functions.values()))
    known = every_field | _AGENT_TOOL_NAMES | _RESULT_FIELDS
    for name, function in functions.items():
        unresolved = set(_IDENTIFIER.findall(_description(function))) - known
        assert not unresolved, f"{name} names {sorted(unresolved)}, which no memory tool offers"


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_search_description_mentions_corpus_only_when_the_schema_offers_it(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    search = _wire_functions(policy, locale, approval)["memory_search_tool"]
    if "corpus" not in _fields(search):
        assert "corpus" not in _description(search)


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_descriptions_offer_only_values_the_schema_accepts(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    functions = _wire_functions(policy, locale, approval)
    accepted: dict[str, set[str]] = {}
    for function in functions.values():
        for field, values in _enum_values(function).items():
            accepted.setdefault(field, set()).update(values)
    for name, function in functions.items():
        for field, value in _FIELD_VALUE.findall(_description(function)):
            if field in accepted:
                assert value in accepted[field], f"{name} offers {field}={value}, which the schema does not accept"


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_save_category_guide_lists_exactly_the_categories_the_schema_accepts(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    save = _wire_functions(policy, locale, approval)["memory_save_tool"]
    assert set(_GUIDE_ENTRY.findall(_description(save))) == _enum_values(save)["category"]


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_save_offers_exactly_the_arguments_the_save_path_reads(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    expected = _SAVE_ARGUMENTS if policy.allow_shared_write else _SAVE_ARGUMENTS - {"write_target"}
    assert _fields(_wire_functions(policy, locale, approval)["memory_save_tool"]) == expected


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_shared_write_target_is_offered_only_when_the_policy_allows_it(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    save = _wire_functions(policy, locale, approval)["memory_save_tool"]
    assert ("write_target" in _fields(save)) is policy.allow_shared_write
    # The block offers the value in quotes; prose such as "shares a preference" is not an offer.
    assert ('"shared"' in _description(save)) is policy.allow_shared_write
    if policy.allow_shared_write:
        assert _enum_values(save)["write_target"] == {"bound", "shared"}


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_wiki_and_sessions_are_mentioned_only_when_the_policy_enables_them(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    functions = _wire_functions(policy, locale, approval)
    for name, function in functions.items():
        description = _description(function)
        if _WIKI.search(description):
            assert policy.allow_wiki, f"{name} mentions wiki, which this policy does not enable"
        if _SESSIONS_SEARCH.search(description):
            assert policy.allow_sessions, f"{name} mentions conversation search, which this policy does not enable"
    search = _description(functions["memory_search_tool"])
    assert bool(_WIKI.search(search)) is policy.allow_wiki
    assert bool(_SESSIONS_SEARCH.search(search)) is policy.allow_sessions


@pytest.mark.parametrize(("policy", "locale", "approval"), _MATRIX)
def test_approval_is_mentioned_only_when_writes_need_it(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    save = _wire_functions(policy, locale, approval)["memory_save_tool"]
    assert ("submitted for approval" in _description(save)) is approval


async def test_mcp_descriptions_name_only_arguments_and_tools_that_exist() -> None:
    manager = MagicMock()
    manager.approval_required = False
    tools = await MemoryMCPServer(manager).mcp.list_tools()
    every_field = {field for tool in tools for field in tool.input_schema.get("properties", {})}
    known = every_field | {tool.name for tool in tools}
    for tool in tools:
        description = tool.description or ""
        unresolved = set(_IDENTIFIER.findall(description)) - known
        assert not unresolved, f"{tool.name} names {sorted(unresolved)}, which no MCP memory tool offers"
        assert "corpus" not in description, tool.name
        assert "wiki_ingest_tool" not in description, tool.name
