"""The one stored shape of a stop reason, and which of two reasons is kept."""

from __future__ import annotations

import pytest

from app.core.agent.stop_reason import merge_stop_reason, normalize_stop_reason, step_item_text, stop_reason_priority


def test_a_stop_reason_is_saved_with_its_code_category_and_message() -> None:
    assert normalize_stop_reason({"code": " engine_limit_reached ", "category": "limit", "message": " Budget spent "}) == {
        "code": "engine_limit_reached",
        "category": "limit",
        "message": "Budget spent",
    }


def test_an_unknown_category_is_saved_as_other_and_a_blank_message_is_made_from_the_code() -> None:
    assert normalize_stop_reason({"code": "agent_cancelled", "category": "bogus", "message": "  "}) == {
        "code": "agent_cancelled",
        "category": "other",
        "message": "agent cancelled",
    }


def test_the_detail_keeps_only_text_keys_and_is_left_out_when_nothing_remains() -> None:
    with_detail = normalize_stop_reason({"code": "error", "detail": {"error_type": "ConnectError", 1: "dropped"}})
    empty_detail = normalize_stop_reason({"code": "error", "detail": {}})
    only_dropped = normalize_stop_reason({"code": "error", "detail": {1: "dropped"}})
    not_a_mapping = normalize_stop_reason({"code": "error", "detail": "text"})

    assert with_detail is not None
    assert with_detail["detail"] == {"error_type": "ConnectError"}
    assert empty_detail is not None
    assert "detail" not in empty_detail
    assert only_dropped is not None
    assert "detail" not in only_dropped
    assert not_a_mapping is not None
    assert "detail" not in not_a_mapping


@pytest.mark.parametrize("raw", [None, "error", ["error"], {}, {"code": ""}, {"code": "   "}, {"code": 5}])
def test_something_that_names_no_code_is_not_a_stop_reason(raw: object) -> None:
    assert normalize_stop_reason(raw) is None


def test_a_limit_outranks_a_cancel_which_outranks_an_error_which_outranks_the_rest() -> None:
    priorities = [stop_reason_priority(code) for code in ("iteration_limit_reached", "agent_cancelled", "error", "other")]

    assert priorities == sorted(priorities, reverse=True)
    assert len(set(priorities)) == 4
    assert stop_reason_priority("engine_limit_reached") == stop_reason_priority("iteration_limit_reached")


def test_the_first_reason_is_kept_when_nothing_came_before() -> None:
    assert merge_stop_reason(None, {"code": "error", "message": "boom"}) == {
        "code": "error",
        "category": "other",
        "message": "boom",
    }


def test_a_stronger_reason_replaces_the_one_kept_and_a_weaker_one_does_not() -> None:
    error = normalize_stop_reason({"code": "error", "category": "error", "message": "boom"})
    limit: dict[str, object] = {"code": "iteration_limit_reached", "category": "limit", "message": "Iteration limit reached"}

    kept = merge_stop_reason(error, limit)
    assert kept is not None
    assert kept["code"] == "iteration_limit_reached"
    assert merge_stop_reason(kept, {"code": "error", "category": "error", "message": "late"}) is kept


def test_a_reason_of_the_same_strength_arriving_later_replaces_the_earlier_one() -> None:
    first = normalize_stop_reason({"code": "error", "category": "error", "message": "first"})

    kept = merge_stop_reason(first, {"code": "error", "category": "error", "message": "second"})

    assert kept is not None
    assert kept["message"] == "second"


def test_a_reason_that_names_no_code_changes_nothing() -> None:
    current = normalize_stop_reason({"code": "error", "message": "boom"})

    assert merge_stop_reason(current, {"code": "  "}) is current
    assert merge_stop_reason(None, {}) is None


def test_the_step_text_is_the_first_non_blank_text_among_the_items() -> None:
    assert step_item_text([{"text": " "}, "skip", {"text": 3}, {"text": " a "}, {"text": "b"}]) == "a"
    assert step_item_text([]) is None
    assert step_item_text("a") is None
    assert step_item_text([{"other": "a"}]) is None
