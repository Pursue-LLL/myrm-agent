"""Unit tests for annotations.py: the hints an MCP server declares and the host's judgment of them.

[INPUT]
- myrm_agent_harness.toolkits.mcp.annotations (POS: declared_annotations, recorded_annotations, judge)
- mcp.types::Tool, ToolAnnotations (POS: the SDK objects a server's declarations arrive in)

[OUTPUT]
- Tests of the three-state reading of a declaration, the read-back from a converted tool, and every rule of ``judge``.

[POS]
Pins the one place a server's self-reported hints turn into host behavior: a claim may tighten, and only a clean
read-only claim may let tools of different servers run side by side.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from types import SimpleNamespace
from typing import cast

import pytest
from mcp.types import Tool, ToolAnnotations

from myrm_agent_harness.core.security.tool_registry import SafetyMetadata
from myrm_agent_harness.toolkits.mcp.annotations import (
    ANNOTATIONS_METADATA_KEY,
    DeclaredAnnotations,
    declared_annotations,
    judge,
    recorded_annotations,
)

_HINTS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def _sdk_tool(**hints: bool) -> Tool:
    return Tool(name="t", input_schema={"type": "object"}, annotations=ToolAnnotations(**hints))


def test_declarations_are_read_from_the_sdk_attributes() -> None:
    tool = _sdk_tool(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

    assert declared_annotations(tool) == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }


def test_a_declared_false_is_kept_and_a_hint_the_server_left_out_is_absent() -> None:
    assert declared_annotations(_sdk_tool(read_only_hint=False)) == {"readOnlyHint": False}
    assert declared_annotations(Tool(name="t", input_schema={"type": "object"})) == {}


def test_declarations_arrive_the_same_from_the_wire_shape() -> None:
    tool = Tool.model_validate(
        {"name": "t", "inputSchema": {"type": "object"}, "annotations": {"readOnlyHint": True, "title": "T"}}
    )

    assert declared_annotations(tool) == {"readOnlyHint": True}


def test_the_wire_spelling_is_read_from_plain_objects_and_mappings() -> None:
    assert declared_annotations(SimpleNamespace(annotations=SimpleNamespace(readOnlyHint=True))) == {
        "readOnlyHint": True
    }
    assert declared_annotations(SimpleNamespace(annotations={"destructiveHint": True})) == {"destructiveHint": True}
    assert declared_annotations(SimpleNamespace(annotations={"destructive_hint": True})) == {"destructiveHint": True}


@pytest.mark.parametrize("value", ["true", "false", 1, 0, None, [], {}])
def test_a_value_that_is_not_a_boolean_is_not_a_declaration(value: object) -> None:
    annotations = {name: value for name in _HINTS}

    assert declared_annotations(SimpleNamespace(annotations=annotations)) == {}


@pytest.mark.parametrize("tool", [SimpleNamespace(), SimpleNamespace(annotations=None), object()])
def test_a_tool_without_annotations_declares_nothing(tool: object) -> None:
    assert declared_annotations(tool) == {}


def test_a_converted_tool_gives_back_what_it_carries() -> None:
    tool = SimpleNamespace(metadata={ANNOTATIONS_METADATA_KEY: {"readOnlyHint": True, "openWorldHint": False}})

    assert recorded_annotations(tool) == {"readOnlyHint": True, "openWorldHint": False}


@pytest.mark.parametrize(
    "tool",
    [
        SimpleNamespace(),
        SimpleNamespace(metadata=None),
        SimpleNamespace(metadata={}),
        SimpleNamespace(metadata={"mcp_output_schema": {"type": "object"}}),
        SimpleNamespace(metadata="not a mapping"),
        SimpleNamespace(metadata={ANNOTATIONS_METADATA_KEY: ["readOnlyHint"]}),
        SimpleNamespace(metadata={"readOnlyHint": True}),
    ],
)
def test_a_tool_that_carries_no_declarations_gives_back_none(tool: object) -> None:
    assert recorded_annotations(tool) == {}


def test_what_a_converted_tool_carries_is_read_back_as_booleans_only() -> None:
    tool = SimpleNamespace(metadata={ANNOTATIONS_METADATA_KEY: {"readOnlyHint": "true", "destructiveHint": True}})

    assert recorded_annotations(tool) == {"destructiveHint": True}


@pytest.mark.parametrize(
    ("declared", "host_serial", "concurrent_safe", "destructive", "claims"),
    [
        pytest.param({}, False, False, False, {}, id="nothing declared"),
        pytest.param({"readOnlyHint": True}, False, True, False, {}, id="read-only"),
        pytest.param(
            {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
            False,
            True,
            False,
            {},
            id="read-only, closed, declared not destructive",
        ),
        pytest.param({"readOnlyHint": True}, True, False, False, {}, id="read-only on a host-serial server"),
        pytest.param(
            {"readOnlyHint": True, "openWorldHint": True},
            False,
            True,
            False,
            {"openWorldHint": True},
            id="read-only reaching outside",
        ),
        pytest.param(
            {"readOnlyHint": False, "destructiveHint": True},
            False,
            False,
            True,
            {"destructiveHint": True},
            id="destructive",
        ),
        pytest.param(
            {"readOnlyHint": True, "destructiveHint": True},
            False,
            False,
            True,
            {"destructiveHint": True},
            id="read-only and destructive contradict each other",
        ),
        pytest.param({"idempotentHint": True}, False, False, False, {}, id="idempotent alone"),
        pytest.param({"readOnlyHint": False}, False, False, False, {}, id="declared writable"),
        pytest.param(
            {"openWorldHint": True, "destructiveHint": True},
            True,
            False,
            True,
            {"destructiveHint": True, "openWorldHint": True},
            id="every tightening claim",
        ),
    ],
)
def test_judge_applies_the_contract(
    declared: DeclaredAnnotations,
    host_serial: bool,
    concurrent_safe: bool,
    destructive: bool,
    claims: dict[str, bool],
) -> None:
    record, shown = judge(declared, host_serial=host_serial)

    assert (record.is_concurrent_safe, record.is_destructive) == (concurrent_safe, destructive)
    assert shown == claims


def _every_declaration() -> list[DeclaredAnnotations]:
    """Each hint is declared true, declared false or left out: 3 ** 4 declarations."""
    return [
        cast(
            DeclaredAnnotations,
            {name: state for name, state in zip(_HINTS, combination, strict=True) if state is not None},
        )
        for combination in itertools.product((None, False, True), repeat=len(_HINTS))
    ]


def test_no_declaration_loosens_anything_but_parallel_scheduling() -> None:
    declarations = _every_declaration()
    assert len(declarations) == 81

    for declared, host_serial in itertools.product(declarations, (False, True)):
        record, claims = judge(declared, host_serial=host_serial)

        # Everything but the two fields below stays as strict as for a tool that declared nothing.
        assert replace(record, is_concurrent_safe=False, is_destructive=False) == SafetyMetadata(), declared
        # A claim that would reassure never reaches the people and the models deciding whether to run a tool.
        assert set(claims) <= {"destructiveHint", "openWorldHint"}, declared
        assert all(value is True for value in claims.values()), declared
        # Parallel scheduling is the one thing a clean read-only claim opens, and a server pin or a contradiction closes.
        clean_read_only = declared.get("readOnlyHint") is True and declared.get("destructiveHint") is not True
        assert record.is_concurrent_safe == (clean_read_only and not host_serial), (declared, host_serial)
        assert record.is_destructive == (declared.get("destructiveHint") is True), declared
