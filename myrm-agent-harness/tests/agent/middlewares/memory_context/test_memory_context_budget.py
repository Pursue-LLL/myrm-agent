"""The memory block's budget helpers: what the renderer kept and charged, and which tools a request binds.

[INPUT]
- agent.middlewares.memory_context.memory_context_budget::render_budgeted_sections, bound_tool_names, memory_search_tool_bound (POS: Internal helper module for memory_context_format: one budget over the memory sections, tag-opener neutralization, and the search-guidance and cold-start prompt texts.)
- agent.security.guards.prompt_budget::BudgetedSection, CHARS_PER_TOKEN (POS: Prompt budgeting data models)

[POS]
Unit guard for the renderer's accounting and for the single reader of the tool names a request binds.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from myrm_agent_harness.agent.middlewares.memory_context.memory_context_budget import (
    bound_tool_names,
    memory_search_tool_bound,
    render_budgeted_sections,
)
from myrm_agent_harness.agent.security.guards.prompt_budget import CHARS_PER_TOKEN, BudgetedSection

_OPENAI_FUNCTION_TOOL = {"type": "function", "function": {"name": "memory_search_tool"}}


def test_a_section_without_items_is_skipped() -> None:
    rendered = render_budgeted_sections(
        [BudgetedSection("Empty", [], priority=1)],
        max_tokens=500,
        truncation_message="X",
    )
    assert rendered.body == ""
    assert rendered.accepted_by_title == {}
    assert rendered.used_chars == 0


def test_a_header_that_does_not_fit_leaves_an_empty_body_and_no_truncation_note() -> None:
    rendered = render_budgeted_sections(
        [BudgetedSection("Wide", ["ok"], priority=1)],
        max_tokens=0,
        truncation_message="SHOULD_NOT_APPEAR",
    )
    assert rendered.body == ""
    assert rendered.used_chars == 0


def test_a_section_whose_first_line_does_not_fit_produces_no_block() -> None:
    rendered = render_budgeted_sections(
        [BudgetedSection("T", ["Z" * 40], priority=1)],
        max_tokens=2,
        truncation_message="",
    )
    assert rendered.body == ""
    assert rendered.accepted_by_title == {}


def test_a_trimmed_body_ends_with_the_truncation_note_and_counts_what_it_kept() -> None:
    rendered = render_budgeted_sections(
        [
            BudgetedSection("High", ["kept-short"], priority=1),
            BudgetedSection("LowPri", ["L" * 8000], priority=80),
        ],
        max_tokens=240,
        truncation_message="CUT_MARKER",
    )
    assert "kept-short" in rendered.body
    assert rendered.body.endswith("CUT_MARKER")
    assert rendered.accepted_by_title == {"High": 1}
    assert rendered.used_chars == len("## High\n") + len("- kept-short\n")


def test_a_section_dropped_between_two_kept_ones_is_not_charged() -> None:
    rendered = render_budgeted_sections(
        [
            BudgetedSection("First", ["a"], priority=1),
            BudgetedSection("Wide", ["W" * 400], priority=2),
            BudgetedSection("Last", ["b"], priority=3),
        ],
        max_tokens=40,
        truncation_message="CUT_MARKER",
    )
    assert rendered.accepted_by_title == {"First": 1, "Last": 1}
    assert "Wide" not in rendered.body
    assert rendered.used_chars == len("## First\n- a\n") + len("## Last\n- b\n")


def test_sections_render_by_ascending_priority_whatever_the_input_order() -> None:
    rendered = render_budgeted_sections(
        [BudgetedSection("Low", ["l"], priority=2), BudgetedSection("High", ["h"], priority=0)],
        max_tokens=500,
        truncation_message="",
    )
    assert rendered.body.index("## High") < rendered.body.index("## Low")


def test_a_tight_budget_drops_the_lower_priority_section_even_when_it_is_listed_first() -> None:
    rendered = render_budgeted_sections(
        [
            BudgetedSection("LowPri", ["L" * 8000], priority=80),
            BudgetedSection("High", ["kept-short"], priority=1),
        ],
        max_tokens=240,
        truncation_message="CUT_MARKER",
    )
    assert rendered.accepted_by_title == {"High": 1}
    assert "LowPri" not in rendered.body


@pytest.mark.parametrize("max_tokens", [10, 60, 240, 1000])
def test_the_characters_used_never_exceed_the_budget(max_tokens: int) -> None:
    sections = [
        BudgetedSection(f"Section {n}", [f"item {n}.{i} " + "x" * (7 * i) for i in range(12)], priority=n)
        for n in range(6)
    ]
    rendered = render_budgeted_sections(sections, max_tokens=max_tokens, truncation_message="CUT")
    assert 0 < rendered.used_chars <= max_tokens * CHARS_PER_TOKEN


def _pinned_section(items: list[str], pinned: set[int]) -> BudgetedSection:
    return BudgetedSection("Rules", items, priority=1, pinned=frozenset(pinned))


def _kept_items(body: str) -> list[str]:
    return [line.removeprefix("- ") for line in body.splitlines() if line.startswith("- ")]


def test_a_cut_drops_unpinned_items_from_the_end_and_keeps_every_pinned_one() -> None:
    items = [f"item {n:02d} " + "x" * 80 for n in range(30)]
    pinned = {5, 28, 29}

    rendered = render_budgeted_sections([_pinned_section(items, pinned)], max_tokens=300, truncation_message="CUT")

    kept = [int(item.split()[1]) for item in _kept_items(rendered.body)]
    assert kept == sorted(kept), "the items keep their order"
    assert pinned <= set(kept)
    kept_unpinned = [n for n in kept if n not in pinned]
    unpinned = [n for n in range(len(items)) if n not in pinned]
    assert kept_unpinned == unpinned[: len(kept_unpinned)]
    assert 0 < len(kept_unpinned) < len(unpinned)
    assert rendered.body.endswith("CUT")
    assert rendered.accepted_by_title == {"Rules": len(kept)}
    assert rendered.used_chars <= 300 * CHARS_PER_TOKEN


def test_the_first_unpinned_item_that_does_not_fit_cuts_every_later_unpinned_item() -> None:
    items = ["a", "B" * 400, "c", "d"]

    rendered = render_budgeted_sections([_pinned_section(items, {3})], max_tokens=40, truncation_message="CUT")

    assert _kept_items(rendered.body) == ["a", "d"]


def test_a_pinned_item_is_dropped_only_when_the_pinned_items_alone_exceed_the_budget() -> None:
    items = ["P" * 150, "Q" * 150, "r"]

    rendered = render_budgeted_sections([_pinned_section(items, {0, 1})], max_tokens=50, truncation_message="CUT")

    assert _kept_items(rendered.body) == ["P" * 150]
    assert rendered.body.endswith("CUT")


def test_pinned_items_that_fit_leave_nothing_to_truncate() -> None:
    rendered = render_budgeted_sections([_pinned_section(["a", "b"], {0})], max_tokens=500, truncation_message="CUT")

    assert _kept_items(rendered.body) == ["a", "b"]
    assert "CUT" not in rendered.body


def _request(tools: object) -> MagicMock:
    return MagicMock(tools=tools)


def test_bound_tool_names_reads_tool_objects_name_dicts_and_openai_function_dicts() -> None:
    tools = [SimpleNamespace(name="bash_tool"), {"name": "write_file"}, _OPENAI_FUNCTION_TOOL]
    assert bound_tool_names(_request(tools)) == {"bash_tool", "write_file", "memory_search_tool"}


def test_bound_tool_names_ignores_entries_without_a_string_name() -> None:
    tools = [
        "bare-string",
        {"type": "func"},
        SimpleNamespace(),
        SimpleNamespace(name=7),
        {"name": 7},
        {"function": "x"},
    ]
    assert bound_tool_names(_request(tools)) == frozenset()


@pytest.mark.parametrize("tools", [None, [], (), "not-a-collection", 5])
def test_bound_tool_names_of_a_request_without_a_tool_list_is_empty(tools: object) -> None:
    assert bound_tool_names(_request(tools)) == frozenset()


def test_memory_search_tool_bound_accepts_objects_dicts_and_function_dicts() -> None:
    assert memory_search_tool_bound(_request([SimpleNamespace(name="memory_search_tool")])) is True
    assert memory_search_tool_bound(_request([{"name": "memory_search_tool"}])) is True
    assert memory_search_tool_bound(_request([_OPENAI_FUNCTION_TOOL])) is True
    others = [SimpleNamespace(name="other_tool"), {"type": "func", "name": "b"}, "bare-string"]
    assert memory_search_tool_bound(_request(others)) is False
    assert memory_search_tool_bound(_request([])) is False
    assert memory_search_tool_bound(_request(None)) is False
