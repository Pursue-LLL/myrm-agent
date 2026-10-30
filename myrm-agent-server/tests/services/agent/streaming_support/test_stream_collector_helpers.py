"""Pure helpers behind what the collector saves: how tool steps merge, how sources are told apart, what a clarification or plan confirmation keeps."""

from __future__ import annotations

import pytest

from app.services.agent.streaming_support.stream_collector_helpers import (
    collect_clarification_required,
    collect_plan_confirmation_status,
    merge_sources_list,
    merge_tasks_step,
    parse_tool_end_result,
    source_dedup_key,
)


def test_a_tool_step_with_a_known_call_id_updates_that_step_instead_of_adding_one() -> None:
    steps: list[dict[str, object]] = []
    first = merge_tasks_step(
        steps,
        {"step_key": "web_search", "tool_name": "web_search", "tool_call_id": "c1", "status": "running", "error": "boom"},
        ["q"],
    )

    again = merge_tasks_step(
        steps,
        {"step_key": "web_search", "tool_name": "web_search", "tool_call_id": " c1 ", "status": "done"},
        ["q", "r"],
    )

    assert again is first
    assert len(steps) == 1
    assert steps[0]["status"] == "done"
    assert steps[0]["items"] == ["q", "r"]
    assert steps[0]["error"] == "boom"


def test_a_step_that_never_got_a_call_id_takes_the_id_of_the_event_with_the_same_key() -> None:
    steps: list[dict[str, object]] = [{"step_key": "shell", "tool_name": "bash", "items": "old"}]

    merged = merge_tasks_step(steps, {"step_key": "shell", "tool_name": "bash", "tool_call_id": "c9"}, "new")

    assert merged is steps[0]
    assert len(steps) == 1
    assert merged["tool_call_id"] == "c9"
    assert merged["items"] == "new"


def test_an_event_without_a_call_id_fills_a_step_without_one_but_not_a_step_that_has_one() -> None:
    steps: list[dict[str, object]] = [{"step_key": "shell", "tool_call_id": "c1", "items": "a"}]

    added = merge_tasks_step(steps, {"step_key": "shell"}, "b")
    filled = merge_tasks_step(steps, {"step_key": "shell"}, "c")

    assert len(steps) == 2
    assert steps[0]["items"] == "a"
    assert filled is added
    assert added["items"] == "c"


def test_the_same_step_key_with_a_different_call_id_is_a_new_step() -> None:
    steps: list[dict[str, object]] = [{"step_key": "shell", "tool_call_id": "c1"}]

    added = merge_tasks_step(steps, {"step_key": "shell", "tool_call_id": "c2"}, "x")

    assert len(steps) == 2
    assert added["tool_call_id"] == "c2"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ({"source_key": " k1 ", "url": "https://a.test"}, "source_key:k1"),
        ({"type": "conversation_history", "conversation_id": " c ", "message_id": "m"}, "conversation:c:m"),
        ({"type": "conversation_history", "conversation_id": "c"}, "conversation:c:"),
        ({"url": " https://a.test "}, "url:https://a.test"),
        ({"skill_name": " search "}, "mcp:search"),
        ({"index": 3, "title": "t"}, "index:3"),
    ],
)
def test_a_source_is_told_apart_by_the_most_specific_thing_it_carries(source: dict[str, object], expected: str) -> None:
    assert source_dedup_key(source) == expected


def test_sources_with_no_identifying_field_are_told_apart_by_their_content() -> None:
    assert source_dedup_key({"title": "t"}) == source_dedup_key({"title": "t"})
    assert source_dedup_key({"title": "t"}) != source_dedup_key({"title": "other"})
    assert source_dedup_key({"title": "t"}).startswith("content:")


def test_a_repeated_source_updates_the_first_one_and_keeps_its_position_number() -> None:
    merged = merge_sources_list(
        [{"url": "https://a.test", "index": 1, "title": "old"}],
        [{"url": "https://a.test", "index": 7, "title": "new"}, {"url": "https://b.test", "index": 2}],
    )

    assert merged == [
        {"url": "https://a.test", "index": 1, "title": "new"},
        {"url": "https://b.test", "index": 2},
    ]


def test_a_tool_result_that_is_not_valid_json_is_ignored_and_other_results_pass_through() -> None:
    assert parse_tool_end_result({"result": "{not json"}) is None
    assert parse_tool_end_result({"result": '{"status": "added"}'}) == {"status": "added"}
    assert parse_tool_end_result({"result": {"status": "added"}}) == {"status": "added"}


def test_a_clarification_keeps_its_options_multiple_choice_flag_and_question() -> None:
    saved = collect_clarification_required(
        {
            "data": {
                "source": "deep_research",
                "options": ["A", " ", "B", 3],
                "allowMultiple": True,
                "prompt": " Pick one ",
            }
        }
    )

    assert saved == {
        "answered": False,
        "source": "deep_research",
        "isResumeMode": False,
        "options": ["A", "B"],
        "allowMultiple": True,
        "question": "Pick one",
    }


def test_the_snake_case_multiple_choice_flag_wins_over_the_camel_case_one() -> None:
    saved = collect_clarification_required({"data": {"allow_multiple": False, "allowMultiple": True, "question": "q"}})

    assert saved is not None
    assert saved["allowMultiple"] is False


@pytest.mark.parametrize("event", [{"data": {}}, {"data": "text"}, {}])
def test_a_clarification_with_nothing_to_ask_is_not_saved(event: dict[str, object]) -> None:
    assert collect_clarification_required(event) is None


def test_a_waiting_plan_is_saved_with_its_items_cost_and_goal() -> None:
    saved = collect_plan_confirmation_status(
        {
            "phase": "plan_confirm",
            "status": "waiting",
            "plan_items": [{"content": " first "}, {"content": "second"}],
            "spawn_count": 3,
            "estimated_cost_usd": 0.123456,
            "remaining_budget_usd": 2,
            "cost_status": " ok ",
            "total_items": 2,
            "goal": " ship ",
        }
    )

    assert saved == {
        "plan": "1. first\n2. second",
        "status": "waiting",
        "source": "deep_research",
        "spawnCount": 3,
        "estimatedCostUsd": 0.1235,
        "remainingBudgetUsd": 2.0,
        "costStatus": "ok",
        "planItems": [{"content": " first "}, {"content": "second"}],
        "totalItems": 2,
        "goal": "ship",
    }


def test_a_waiting_plan_text_is_preferred_over_the_numbered_items_and_keeps_its_source() -> None:
    saved = collect_plan_confirmation_status(
        {
            "phase": "plan_confirm",
            "status": "waiting",
            "plan": " the plan ",
            "plan_items": [{"content": "ignored"}],
            "source": "chat",
        }
    )

    assert saved is not None
    assert saved["plan"] == "the plan"
    assert saved["source"] == "chat"


@pytest.mark.parametrize(("modified", "status"), [(True, "edited"), (False, "confirmed"), (None, "confirmed")])
def test_a_resolved_plan_is_saved_as_edited_or_confirmed(modified: bool | None, status: str) -> None:
    saved = collect_plan_confirmation_status({"phase": "plan_confirm", "status": "resolved", "modified": modified})

    assert saved == {"status": status}


@pytest.mark.parametrize(
    "data",
    [
        {"phase": "research", "status": "waiting"},
        {"phase": "plan_confirm", "status": 3},
        {"phase": "plan_confirm", "status": "cancelled"},
    ],
)
def test_other_phases_and_unknown_plan_statuses_are_not_saved(data: dict[str, object]) -> None:
    assert collect_plan_confirmation_status(data) is None
