"""Direct delegation: how the end of an external agent's turn reaches the frontend.

Status and continuity notices, the turn limit, a failed turn, and a stop from the user.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.types import (
    IMAGES_NOT_SENT_STATUS,
    AcpErrorCode,
    ContinuityStatus,
    RuntimeEvent,
    RuntimeEventType,
)
from myrm_agent_harness.utils import CancellationToken

from app.services.external_agents.delegation.stream import stream_direct_delegate
from tests.support.scripted_delegation import (
    CANCELLED,
    MESSAGE_END,
    STEPS,
    ScriptedPool,
    event_types,
    playing,
    scripted_error,
    scripted_event,
    step_text,
    steps_of,
    stream_turn,
)


@pytest.mark.parametrize("continuity", list(ContinuityStatus))
async def test_a_continuity_status_becomes_a_title_only_notice(continuity: ContinuityStatus) -> None:
    pool = ScriptedPool(playing(scripted_event(RuntimeEventType.STATUS_UPDATE, status=str(continuity))))

    (notice,) = steps_of(await stream_turn(pool), f"delegation_claude_{continuity.value}")

    assert notice == {
        "type": STEPS,
        "step_key": f"delegation_claude_{continuity.value}",
        "tool_name": "delegate:claude",
        "status": "completed",
        "data": [],
    }


async def test_images_that_were_not_handed_to_the_agent_become_a_title_only_notice() -> None:
    pool = ScriptedPool(playing(scripted_event(RuntimeEventType.STATUS_UPDATE, status=IMAGES_NOT_SENT_STATUS, images=2)))

    events = await stream_turn(pool)

    (notice,) = steps_of(events, "delegation_claude_images_not_sent")
    assert notice == {
        "type": STEPS,
        "step_key": "delegation_claude_images_not_sent",
        "tool_name": "delegate:claude",
        "status": "completed",
        "data": [],
    }
    # Only the opening and closing lines of the status step: the notice is not one more update of it.
    assert len(steps_of(events, "delegation_claude_status")) == 2


async def test_a_status_update_shows_only_what_the_cli_itself_said() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.STATUS_UPDATE, status="working", message="1m 05s"),
            scripted_event(RuntimeEventType.STATUS_UPDATE, status="warning", message="slow"),
        )
    )

    _, working, warning, _ = steps_of(await stream_turn(pool), "delegation_claude_status")

    assert (step_text(working), step_text(warning)) == ("1m 05s", "slow")
    assert "status" not in working and "status" not in warning


@pytest.mark.parametrize(
    "update",
    [
        {"status": "starting"},
        {"status": "starting", "message": "Spawning ACP agent process"},
        {"status": "working"},
        {"status": "working", "message": 5},
        {"status": "something_new", "message": "text of ours"},
    ],
)
async def test_a_status_update_with_nothing_for_the_user_leaves_the_status_step_without_text(update: dict[str, object]) -> None:
    pool = ScriptedPool(playing(scripted_event(RuntimeEventType.STATUS_UPDATE, **update)))

    _, step, _ = steps_of(await stream_turn(pool), "delegation_claude_status")

    assert step["data"] == []


async def test_reaching_the_turn_limit_is_a_stop_and_not_an_error() -> None:
    pool = ScriptedPool(
        playing(scripted_event(RuntimeEventType.TEXT_DELTA, content="half"), scripted_error(AcpErrorCode.MAX_TURNS))
    )

    events = await stream_turn(pool)

    assert AgentEventType.ERROR.value not in event_types(events)
    status, notice = events[-3], events[-2]
    assert (status["step_key"], status["status"], status["data"]) == ("delegation_claude_status", "completed", [])
    # The sentence is the frontend's, in the user's language: a title-only, already finished step.
    assert notice == {
        "type": STEPS,
        "step_key": "delegation_claude_turn_limit",
        "tool_name": "delegate:claude",
        "status": "completed",
        "data": [],
    }
    assert events[-1]["type"] == MESSAGE_END


async def test_a_failed_turn_reports_the_error_and_marks_its_last_step_failed() -> None:
    pool = ScriptedPool(playing(scripted_error(AcpErrorCode.PROCESS_CRASHED, "claude exited with code 1")))

    events = await stream_turn(pool)

    assert [event for event in events if event["type"] == AgentEventType.ERROR.value] == [
        {"type": AgentEventType.ERROR.value, "data": "claude exited with code 1"}
    ]
    assert (events[-2]["step_key"], events[-2]["status"], events[-2]["data"]) == ("delegation_claude_status", "error", [])
    assert events[-1]["type"] == MESSAGE_END


async def test_an_error_without_details_is_reported_as_unknown() -> None:
    pool = ScriptedPool(playing(scripted_event(RuntimeEventType.ERROR, error=None)))

    assert {"type": AgentEventType.ERROR.value, "data": "Unknown error"} in await stream_turn(pool)


async def test_a_turn_the_backend_reports_cancelled_ends_cancelled() -> None:
    pool = ScriptedPool(
        playing(
            scripted_event(RuntimeEventType.TEXT_DELTA, content="part"),
            scripted_error(AcpErrorCode.CANCELLED),
            scripted_event(RuntimeEventType.TEXT_DELTA, content="late"),
        )
    )

    events = await stream_turn(pool)

    assert event_types(events) == [STEPS, AgentEventType.MESSAGE.value, CANCELLED]


async def test_a_stop_reaches_an_external_agent_that_is_silent() -> None:
    """The stream blocks on a CLI that prints nothing; the stop button must still kill it."""

    async def silent_until_cancelled(pool: ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        yield scripted_event(RuntimeEventType.TEXT_DELTA, content="working")
        await pool.cancel_called.wait()

    pool = ScriptedPool(silent_until_cancelled)
    token = CancellationToken()
    stream = asyncio.create_task(stream_turn(pool, token))

    await asyncio.sleep(0.05)
    assert not pool.cancelled
    token.cancel()
    events = await asyncio.wait_for(stream, timeout=5)

    assert pool.cancelled == [("claude", "claude-chat-1")]
    assert event_types(events) == [STEPS, AgentEventType.MESSAGE.value, CANCELLED]


async def test_a_stop_between_events_cancels_the_turn() -> None:
    token = CancellationToken()

    async def turn(_pool: ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        token.cancel()
        yield scripted_event(RuntimeEventType.TEXT_DELTA, content="partial")

    pool = ScriptedPool(turn)

    events = await stream_turn(pool, token)

    assert pool.cancelled == [("claude", "claude-chat-1")]
    assert event_types(events) == [STEPS, CANCELLED]


async def test_a_stop_after_the_last_event_is_still_a_cancel() -> None:
    token = CancellationToken()

    async def turn(_pool: ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        yield scripted_event(RuntimeEventType.TEXT_DELTA, content="done")
        token.cancel()

    events = await stream_turn(ScriptedPool(turn), token)

    assert event_types(events) == [STEPS, AgentEventType.MESSAGE.value, CANCELLED]


async def test_closing_the_stream_closes_the_turn_at_once() -> None:
    """A client that went away stops the external process now, not whenever the garbage collector runs."""
    closed = asyncio.Event()

    async def turn(_pool: ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        try:
            while True:
                yield scripted_event(RuntimeEventType.TEXT_DELTA, content="more")
        finally:
            closed.set()

    stream = stream_direct_delegate(ScriptedPool(turn), "claude", "do it", session_id="claude-chat-1")
    await anext(stream)
    await anext(stream)

    await stream.aclose()

    assert closed.is_set()
