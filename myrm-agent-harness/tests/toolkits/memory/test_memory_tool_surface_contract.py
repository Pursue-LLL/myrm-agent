"""What the memory tool descriptions say about the tools' own surface is true under the active policy.

A description is prompt text the model acts on: naming an argument, tool or corpus it cannot use sends it into a dead
end. The matrix builds the real tools for every corpus policy, locale and approval mode and holds each description
against the schemas the provider receives (the MCP surface against the MCP server's own tool schemas).
"""

from __future__ import annotations

import itertools
import re
from typing import cast
from unittest.mock import MagicMock

import pytest
from langchain_core.tools import BaseTool

from myrm_agent_harness.toolkits.llms.adapters.chat_model.binding import tool_bind_kwargs
from myrm_agent_harness.toolkits.memory.agent_surface.mcp_server.server import MemoryMCPServer
from myrm_agent_harness.toolkits.memory.agent_surface.memory_agent_tools.factory import create_memory_tools
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import MemorySearchPolicy

_IDENTIFIER = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CORPUS_VALUE = re.compile(r"corpus=([a-z]+)")
_WIKI = re.compile("wiki", re.IGNORECASE)
# The word "sessions" also means plain chat sessions in prose, so conversation search is recognised by what only it has.
_SESSIONS_SEARCH = re.compile(r"corpus=sessions|expand_\w+|\bmessage_id\b|^- sessions[:：]", re.MULTILINE)
_AGENT_TOOL_NAMES = {"memory_search_tool", "memory_save_tool", "memory_manage_tool", "wiki_ingest_tool"}
# A field of the sessions hit the model reads, not an argument it passes.
_RESULT_FIELDS = {"message_id"}

_POLICIES = [
    pytest.param(MemorySearchPolicy(), id="memory-only"),
    pytest.param(MemorySearchPolicy(allow_wiki=True), id="wiki"),
    pytest.param(MemorySearchPolicy(allow_sessions=True), id="sessions"),
    pytest.param(MemorySearchPolicy(allow_wiki=True, allow_sessions=True), id="wiki-and-sessions"),
]
_MATRIX = [
    pytest.param(policy.values[0], locale, approval, id=f"{policy.id}-{locale}-{'approval' if approval else 'direct'}")
    for policy, locale, approval in itertools.product(_POLICIES, ("en", "zh"), (False, True))
]

type WireFunction = dict[str, object]


def _wire_functions(policy: MemorySearchPolicy, locale: str, approval_required: bool) -> dict[str, WireFunction]:
    """The memory tools as ``tool_bind_kwargs`` hands them to the provider, by tool name."""
    manager = MagicMock()
    manager.approval_required = approval_required
    tools = cast(list[BaseTool], create_memory_tools(manager, search_policy=policy, description_locale=locale))
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
def test_search_description_routes_only_to_corpora_the_schema_offers(
    policy: MemorySearchPolicy, locale: str, approval: bool
) -> None:
    search = _wire_functions(policy, locale, approval)["memory_search_tool"]
    properties = cast(dict[str, dict[str, object]], cast(dict[str, object], search["parameters"])["properties"])
    routed = set(_CORPUS_VALUE.findall(_description(search)))
    if "corpus" in properties:
        assert routed <= set(cast(list[str], properties["corpus"]["enum"]))
    else:
        assert not routed
        assert "corpus" not in _description(search)


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
