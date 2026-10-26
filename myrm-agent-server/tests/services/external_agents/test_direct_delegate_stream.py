"""Direct delegation: how the events of an external agent's turn reach the frontend."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Callable

import pytest
from myrm_agent_harness.api import AgentEventType
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    AuthMode,
    ContinuityStatus,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)
from myrm_agent_harness.utils import CancellationToken

from app.services.external_agents.direct_delegate_stream import SseEvent, _token_count, stream_direct_delegate

TurnScript = Callable[["_ScriptedPool"], AsyncGenerator[RuntimeEvent]]

_STEPS = AgentEventType.TASKS_STEPS.value
_CANCELLED = AgentEventType.CANCELLED.value
_MESSAGE_END = AgentEventType.MESSAGE_END.value


class _ScriptedPool:
    """A ``DelegationPool`` whose turn plays a script and records how the stream drove it."""

    def __init__(self, turn: TurnScript, *, auth_mode: AuthMode | None = "subscription") -> None:
        self._turn = turn
        self._config = RuntimeConfig(backend_type="cli", auth_mode=auth_mode) if auth_mode else None
        self.turns: list[tuple[str, str, str]] = []
        self.cancelled: list[tuple[str, str]] = []
        self.cancel_called = asyncio.Event()

    @property
    def available_backends(self) -> list[str]:
        return ["claude"]

    def get_config(self, name: str) -> RuntimeConfig | None:
        return self._config

    def run_turn(
        self, name: str, prompt: str, session_id: str, *, mode: str = "persistent", mcp_servers: object = None
    ) -> AsyncGenerator[RuntimeEvent]:
        self.turns.append((name, prompt, session_id))
        return self._turn(self)

    async def cancel(self, name: str, session_id: str) -> None:
        self.cancelled.append((name, session_id))
        self.cancel_called.set()


def _event(event_type: RuntimeEventType, **data: object) -> RuntimeEvent:
    return create_event(event_type, "claude-chat-1", **data)


def _error(code: AcpErrorCode, message: str = "it broke") -> RuntimeEvent:
    return _event(RuntimeEventType.ERROR, error=AcpError(code=code, message=message))


def _playing(*events: RuntimeEvent) -> TurnScript:
    async def turn(_pool: _ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        for event in events:
            yield event

    return turn


async def _stream(pool: _ScriptedPool, token: CancellationToken | None = None) -> list[SseEvent]:
    return [
        event async for event in stream_direct_delegate(pool, "claude", "do it", session_id="claude-chat-1", cancel_token=token)
    ]


def _types(events: list[SseEvent]) -> list[object]:
    return [event["type"] for event in events]


def _steps(events: list[SseEvent], step_key: str) -> list[SseEvent]:
    return [event for event in events if event["type"] == _STEPS and event["step_key"] == step_key]


def _line(step: SseEvent) -> object:
    data = step["data"]
    assert isinstance(data, list) and len(data) == 1
    return data[0]["text"]


async def test_the_turn_runs_the_prompt_on_the_given_session() -> None:
    pool = _ScriptedPool(_playing())

    await _stream(pool)

    assert pool.turns == [("claude", "do it", "claude-chat-1")]


async def test_a_turn_streams_its_text_and_reasoning_between_a_connecting_and_a_completed_step() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.REASONING_DELTA, content="hmm"),
            _event(RuntimeEventType.TEXT_DELTA, content="hello"),
        )
    )

    events = await _stream(pool)

    assert [(event["type"], event.get("data")) for event in events] == [
        (_STEPS, [{"text": "claude: connecting"}]),
        (AgentEventType.REASONING.value, {"content": "hmm", "source": "delegate:claude"}),
        (AgentEventType.MESSAGE.value, "hello"),
        (_STEPS, [{"text": "claude: completed"}]),
        (_MESSAGE_END, ""),
    ]
    assert events[-2]["step_key"] == "delegation_claude_status"
    assert events[-2]["status"] == "completed"


async def test_deltas_without_text_are_dropped() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TEXT_DELTA, content=None),
            _event(RuntimeEventType.REASONING_DELTA, content=3),
            _event(RuntimeEventType.DONE),
        )
    )

    assert _types(await _stream(pool)) == [_STEPS, _STEPS, _MESSAGE_END]


@pytest.mark.parametrize(("auth_mode", "billable"), [("api_key", True), ("subscription", False), (None, False)])
async def test_usage_is_billable_only_for_an_api_key(auth_mode: AuthMode | None, billable: bool) -> None:
    pool = _ScriptedPool(_playing(_event(RuntimeEventType.USAGE_UPDATE, input_tokens=3, output_tokens=4)), auth_mode=auth_mode)

    usage = [event for event in await _stream(pool) if event["type"] == AgentEventType.TOKEN_USAGE.value]

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
    pool = _ScriptedPool(_playing(_event(RuntimeEventType.USAGE_UPDATE, **tokens)))

    assert AgentEventType.TOKEN_USAGE.value not in _types(await _stream(pool))


def test_token_counts_accept_plain_numbers_only() -> None:
    assert _token_count(12) == 12
    assert _token_count(12.9) == 12
    assert _token_count(None) == 0
    assert _token_count(True) == 0
    assert _token_count("12") == 0


async def test_a_tool_call_is_one_step_that_its_result_updates() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TOOL_START, tool_name="Read", tool_call_id="t1", summary="a.txt"),
            _event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1", output="contents", is_error=False),
        )
    )

    started, finished = _steps(await _stream(pool), "delegation_claude_tool")

    assert started == {
        "type": _STEPS,
        "step_key": "delegation_claude_tool",
        "tool_name": "delegate:claude",
        "tool_call_id": "t1",
        "data": [{"text": "claude: Read — a.txt"}],
    }
    # The frontend replaces a step's items with what the update carries, so the result repeats the line.
    assert finished == {**started, "status": "completed"}


async def test_a_failed_tool_call_carries_the_start_of_its_error_text() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TOOL_START, tool_name="Bash", tool_call_id="t1"),
            _event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1", output=f"  {'x' * 1000}\n", is_error=True),
        )
    )

    _, finished = _steps(await _stream(pool), "delegation_claude_tool")

    assert finished["status"] == "error"
    assert finished["error"] == "x" * 300
    assert _line(finished) == "claude: Bash"


async def test_a_failed_tool_call_without_output_has_no_error_text() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TOOL_START, tool_name="Bash", tool_call_id="t1"),
            _event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1", is_error=True),
        )
    )

    _, finished = _steps(await _stream(pool), "delegation_claude_tool")

    assert finished["status"] == "error"
    assert "error" not in finished


async def test_overlapping_tool_calls_keep_their_own_lines() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TOOL_START, tool_name="Read", tool_call_id="t1", summary="a.txt"),
            _event(RuntimeEventType.TOOL_START, tool_name="Grep", tool_call_id="t2", summary="todo"),
            _event(RuntimeEventType.TOOL_RESULT, tool_call_id="t2"),
            _event(RuntimeEventType.TOOL_RESULT, tool_call_id="t1"),
        )
    )

    steps = _steps(await _stream(pool), "delegation_claude_tool")

    assert [(step["tool_call_id"], _line(step), step.get("status")) for step in steps] == [
        ("t1", "claude: Read — a.txt", None),
        ("t2", "claude: Grep — todo", None),
        ("t2", "claude: Grep — todo", "completed"),
        ("t1", "claude: Read — a.txt", "completed"),
    ]


async def test_a_tool_call_without_an_id_pairs_its_result_by_order() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TOOL_START, tool_name="shell"),
            _event(RuntimeEventType.TOOL_RESULT, is_error=False),
        )
    )

    started, finished = _steps(await _stream(pool), "delegation_claude_tool")

    assert "tool_call_id" not in started and "tool_call_id" not in finished
    assert _line(finished) == _line(started) == "claude: shell"
    assert finished["status"] == "completed"


async def test_a_result_without_a_start_describes_itself() -> None:
    pool = _ScriptedPool(
        _playing(_event(RuntimeEventType.TOOL_RESULT, tool_call_id="c1", output="add a.txt, update b.py", is_error=False))
    )

    (step,) = _steps(await _stream(pool), "delegation_claude_tool")

    assert _line(step) == "claude: tool — add a.txt, update b.py"
    assert step["status"] == "completed"


@pytest.mark.parametrize("continuity", list(ContinuityStatus))
async def test_a_continuity_status_becomes_a_title_only_notice(continuity: ContinuityStatus) -> None:
    pool = _ScriptedPool(_playing(_event(RuntimeEventType.STATUS_UPDATE, status=str(continuity))))

    (notice,) = _steps(await _stream(pool), f"delegation_claude_{continuity.value}")

    assert notice == {
        "type": _STEPS,
        "step_key": f"delegation_claude_{continuity.value}",
        "tool_name": "delegate:claude",
        "status": "completed",
        "data": [],
    }


async def test_any_other_status_update_is_a_status_line() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.STATUS_UPDATE, status="starting"),
            _event(RuntimeEventType.STATUS_UPDATE, status="warning", message="slow"),
        )
    )

    _, starting, warning, _ = _steps(await _stream(pool), "delegation_claude_status")

    assert (_line(starting), _line(warning)) == ("claude: starting", "claude: warning — slow")
    assert "status" not in starting


async def test_reaching_the_turn_limit_is_a_stop_and_not_an_error() -> None:
    pool = _ScriptedPool(_playing(_event(RuntimeEventType.TEXT_DELTA, content="half"), _error(AcpErrorCode.MAX_TURNS)))

    events = await _stream(pool)

    assert AgentEventType.ERROR.value not in _types(events)
    assert (_line(events[-2]), events[-2]["status"]) == ("claude: stopped at its turn limit", "completed")
    assert events[-1]["type"] == _MESSAGE_END


async def test_a_failed_turn_reports_the_error_and_marks_its_last_step_failed() -> None:
    pool = _ScriptedPool(_playing(_error(AcpErrorCode.PROCESS_CRASHED, "claude exited with code 1")))

    events = await _stream(pool)

    assert [event for event in events if event["type"] == AgentEventType.ERROR.value] == [
        {"type": AgentEventType.ERROR.value, "data": "claude exited with code 1"}
    ]
    assert (_line(events[-2]), events[-2]["status"]) == ("claude: failed", "error")
    assert events[-1]["type"] == _MESSAGE_END


async def test_an_error_without_details_is_reported_as_unknown() -> None:
    pool = _ScriptedPool(_playing(_event(RuntimeEventType.ERROR, error=None)))

    assert {"type": AgentEventType.ERROR.value, "data": "Unknown error"} in await _stream(pool)


async def test_a_turn_the_backend_reports_cancelled_ends_cancelled() -> None:
    pool = _ScriptedPool(
        _playing(
            _event(RuntimeEventType.TEXT_DELTA, content="part"),
            _error(AcpErrorCode.CANCELLED),
            _event(RuntimeEventType.TEXT_DELTA, content="late"),
        )
    )

    events = await _stream(pool)

    assert _types(events) == [_STEPS, AgentEventType.MESSAGE.value, _CANCELLED]


async def test_a_stop_reaches_an_external_agent_that_is_silent() -> None:
    """The stream blocks on a CLI that prints nothing; the stop button must still kill it."""

    async def silent_until_cancelled(pool: _ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        yield _event(RuntimeEventType.TEXT_DELTA, content="working")
        await pool.cancel_called.wait()

    pool = _ScriptedPool(silent_until_cancelled)
    token = CancellationToken()
    stream = asyncio.create_task(_stream(pool, token))

    await asyncio.sleep(0.05)
    assert not pool.cancelled
    token.cancel()
    events = await asyncio.wait_for(stream, timeout=5)

    assert pool.cancelled == [("claude", "claude-chat-1")]
    assert _types(events) == [_STEPS, AgentEventType.MESSAGE.value, _CANCELLED]


async def test_a_stop_between_events_cancels_the_turn() -> None:
    token = CancellationToken()

    async def turn(_pool: _ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        token.cancel()
        yield _event(RuntimeEventType.TEXT_DELTA, content="partial")

    pool = _ScriptedPool(turn)

    events = await _stream(pool, token)

    assert pool.cancelled == [("claude", "claude-chat-1")]
    assert _types(events) == [_STEPS, _CANCELLED]


async def test_a_stop_after_the_last_event_is_still_a_cancel() -> None:
    token = CancellationToken()

    async def turn(_pool: _ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        yield _event(RuntimeEventType.TEXT_DELTA, content="done")
        token.cancel()

    events = await _stream(_ScriptedPool(turn), token)

    assert _types(events) == [_STEPS, AgentEventType.MESSAGE.value, _CANCELLED]


async def test_closing_the_stream_closes_the_turn_at_once() -> None:
    """A client that went away stops the external process now, not whenever the garbage collector runs."""
    closed = asyncio.Event()

    async def turn(_pool: _ScriptedPool) -> AsyncGenerator[RuntimeEvent]:
        try:
            while True:
                yield _event(RuntimeEventType.TEXT_DELTA, content="more")
        finally:
            closed.set()

    stream = stream_direct_delegate(_ScriptedPool(turn), "claude", "do it", session_id="claude-chat-1")
    await anext(stream)
    await anext(stream)

    await stream.aclose()

    assert closed.is_set()
