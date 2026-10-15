"""Stream contract that links a committed skill_manage batch to the Task Steps entry of its call."""

from __future__ import annotations

from app.services.skills.mutation_batch_stream import BATCH_ID_FIELD, build_batch_committed_event, link_batch_to_step

FIRST = "a1b2c3d4-e5f6-4789-a012-3456789abcde"
SECOND = "b1b2c3d4-e5f6-4789-b012-3456789abcde"


def _step(tool_name: str = "skill_manage_tool", **fields: object) -> dict[str, object]:
    return {"tool_name": tool_name, **fields}


def test_event_is_a_tool_end_of_the_skill_manage_tool_carrying_the_batch() -> None:
    assert build_batch_committed_event(FIRST) == {
        "type": "tool_end",
        "tool_name": "skill_manage_tool",
        BATCH_ID_FIELD: FIRST,
    }


def test_batch_links_to_the_latest_skill_manage_step_without_a_batch() -> None:
    steps = [_step(tool_call_id="older"), _step(tool_call_id="newer")]

    assert link_batch_to_step(steps, build_batch_committed_event(FIRST)) is True

    assert steps[1][BATCH_ID_FIELD] == FIRST
    assert BATCH_ID_FIELD not in steps[0]


def test_consecutive_batches_each_claim_their_own_step() -> None:
    steps = [_step(tool_call_id="first-call")]
    link_batch_to_step(steps, build_batch_committed_event(FIRST))
    steps.append(_step(tool_call_id="second-call"))

    link_batch_to_step(steps, build_batch_committed_event(SECOND))

    assert [step[BATCH_ID_FIELD] for step in steps] == [FIRST, SECOND]


def test_namespaced_skill_manage_tool_name_matches() -> None:
    steps = [_step(tool_name="agent_x__skill_manage_tool")]

    assert link_batch_to_step(steps, build_batch_committed_event(FIRST)) is True


def test_failed_and_foreign_steps_are_never_linked() -> None:
    steps = [_step("bash_code_execute_tool"), _step(status="error"), _step(status="cancelled")]

    assert link_batch_to_step(steps, build_batch_committed_event(FIRST)) is False

    assert all(BATCH_ID_FIELD not in step for step in steps)


def test_batch_without_any_step_to_claim_it_links_nothing() -> None:
    assert link_batch_to_step([], build_batch_committed_event(FIRST)) is False


def test_batch_id_is_stored_lowercase() -> None:
    steps = [_step()]

    link_batch_to_step(steps, build_batch_committed_event(FIRST.upper()))

    assert steps[0][BATCH_ID_FIELD] == FIRST


def test_malformed_or_missing_batch_ids_are_ignored() -> None:
    steps = [_step()]
    for event in (
        build_batch_committed_event("not-a-uuid"),
        {"type": "tool_end", "tool_name": "skill_manage_tool", BATCH_ID_FIELD: 42},
        {"type": "tool_end", "tool_name": "skill_manage_tool"},
    ):
        assert link_batch_to_step(steps, event) is False

    assert BATCH_ID_FIELD not in steps[0]


def test_event_of_another_tool_is_ignored() -> None:
    steps = [_step()]
    event = {"type": "tool_end", "tool_name": "memory_search_tool", BATCH_ID_FIELD: FIRST}

    assert link_batch_to_step(steps, event) is False

    assert BATCH_ID_FIELD not in steps[0]
