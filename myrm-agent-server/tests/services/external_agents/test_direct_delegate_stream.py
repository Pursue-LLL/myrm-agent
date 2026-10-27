"""Direct delegation: how an external agent's text, reasoning, usage and tool calls reach the frontend."""

from __future__ import annotations

import pytest
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.types import AuthMode, RuntimeEventType

from app.services.external_agents.direct_delegate_stream import _token_count
from tests.support.scripted_delegation import (
    MESSAGE_END,
    STEPS,
    ScriptedPool,
    event_types,
    playing,
    scripted_event,
    step_text,
    steps_of,
    stream_turn,
)


async def test_the_turn_runs_the_prompt_on_the_given_session() -> None:
    pool = ScriptedPool(playing())

    await stream_turn(pool)

    assert pool.turns == [("claude", "do it", "claude-chat-1")]


async def test_a_turn_streams_its_text_and_reasoning_between_a_running_and_a_completed_status_step() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.REASONING_DELTA, content="hmm"),
            scripted_event(RuntimeEventType.TEXT_DELTA, content="hello"),
        )
    )

    events = await stream_turn(pool)

    # The status step carries no wording of ours: the frontend words its title in the user's language.
    assert [(event["type"], event.get("data")) for event in events] == [
        (STEPS, []),
        (AgentEventType.REASONING.value, {"content": "hmm", "source": "delegate:claude"}),
        (AgentEventType.MESSAGE.value, "hello"),
        (STEPS, []),
        (MESSAGE_END, ""),
    ]
    assert "status" not in events[0]
    assert events[-2]["step_key"] == "delegation_claude_status"
    assert events[-2]["status"] == "completed"


async def test_deltas_without_text_are_dropped() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TEXT_DELTA, content=None),
            scripted_event(RuntimeEventType.REASONING_DELTA, content=3),
            scripted_event(RuntimeEventType.DONE),
        )
    )

    assert event_types(await stream_turn(pool)) == [STEPS, STEPS, MESSAGE_END]


@pytest.mark.parametrize(("auth_mode", "billable"), [("api_key", True), ("subscription", False), (None, False)])
async def test_usage_is_billable_only_for_an_api_key(auth_mode: AuthMode | None, billable: bool) -> None:
    pool = ScriptedPool(
        playing(scripted_event(RuntimeEventType.USAGE_UPDATE, input_tokens=3, output_tokens=4)), auth_mode=auth_mode
    )

    usage = [event for event in await stream_turn(pool) if event["type"] == AgentEventType.TOKEN_USAGE.value]

    assert usage == [
        {
            "type": AgentEventType.TOKEN_USAGE.value,
            "data": {
                "source": "delegate:claude",
                "input_tokens": 3,
                "output_tokens": 4,
                "total_tokens": 7,
                "auth_mode": auth_mode or "subscription",
                "billable": billable,
            },
        }
    ]


@pytest.mark.parametrize("tokens", [{}, {"input_tokens": 0, "output_tokens": 0}, {"input_tokens": "9", "output_tokens": True}])
async def test_usage_without_tokens_is_not_reported(tokens: dict[str, object]) -> None:
    pool = ScriptedPool(playing(scripted_event(RuntimeEventType.USAGE_UPDATE, **tokens)))

    assert AgentEventType.TOKEN_USAGE.value not in event_types(await stream_turn(pool))


def test_token_counts_accept_plain_numbers_only() -> None:
    assert _token_count(12) == 12
    assert _token_count(12.9) == 12
    assert _token_count(None) == 0
    assert _token_count(True) == 0
    assert _token_count("12") == 0


async def test_a_tool_call_is_one_step_that_its_result_updates() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TOOL_START, tool_name="Read", tool_call_id="t1", summary="a.txt"),
            scripted_event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1", output="contents", is_error=False),
        )
    )

    started, finished = steps_of(await stream_turn(pool), "delegation_claude_tool")

    assert started == {
        "type": STEPS,
        "step_key": "delegation_claude_tool",
        "tool_name": "delegate:claude",
        "tool_call_id": "t1",
        "data": [{"text": "claude: Read — a.txt"}],
    }
    # The frontend replaces a step's items with what the update carries, so the result repeats the line.
    assert finished == {**started, "status": "completed"}


async def test_a_failed_tool_call_carries_the_start_of_its_error_text() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TOOL_START, tool_name="Bash", tool_call_id="t1"),
            scripted_event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1", output=f"  {'x' * 1000}\n", is_error=True),
        )
    )

    _, finished = steps_of(await stream_turn(pool), "delegation_claude_tool")

    assert finished["status"] == "error"
    assert finished["error"] == "x" * 300
    assert step_text(finished) == "claude: Bash"


async def test_a_failed_tool_call_without_output_has_no_error_text() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TOOL_START, tool_name="Bash", tool_call_id="t1"),
            scripted_event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1", is_error=True),
        )
    )

    _, finished = steps_of(await stream_turn(pool), "delegation_claude_tool")

    assert finished["status"] == "error"
    assert "error" not in finished


async def test_overlapping_tool_calls_keep_their_own_lines() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TOOL_START, tool_name="Read", tool_call_id="t1", summary="a.txt"),
            scripted_event(RuntimeEventType.TOOL_START, tool_name="Grep", tool_call_id="t2", summary="todo"),
            scripted_event(RuntimeEventType.TOOL_RESULT, tool_call_id="t2"),
            scripted_event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1"),
        )
    )

    steps = steps_of(await stream_turn(pool), "delegation_claude_tool")

    assert [(step["tool_call_id"], step_text(step), step.get("status")) for step in steps] == [
        ("t1", "claude: Read — a.txt", None),
        ("t2", "claude: Grep — todo", None),
        ("t2", "claude: Grep — todo", "completed"),
        ("t1", "claude: Read — a.txt", "completed"),
    ]


async def test_a_tool_call_without_an_id_pairs_its_result_by_order() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TOOL_START, tool_name="shell"),
            scripted_event(RuntimeEventType.TOOL_RESULT, is_error=False),
        )
    )

    started, finished = steps_of(await stream_turn(pool), "delegation_claude_tool")

    assert "tool_call_id" not in started and "tool_call_id" not in finished
    assert step_text(finished) == step_text(started) == "claude: shell"
    assert finished["status"] == "completed"


async def test_a_result_without_a_start_describes_itself() -> None:
    pool = ScriptedPool(
        playing(scripted_event(RuntimeEventType.TOOL_RESULT, tool_call_id="c1", output="add a.txt, update b.py", is_error=False))
    )

    (step,) = steps_of(await stream_turn(pool), "delegation_claude_tool")

    assert step_text(step) == "claude: tool — add a.txt, update b.py"
    assert step["status"] == "completed"
