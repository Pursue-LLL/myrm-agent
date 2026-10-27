"""A stopped request is never retried, and a call still running when it is stopped does not outlive the request.

The retry would run again a call the user already stopped; a call that only watches its own deadline would keep going
(and keep its side effects) long after the turn ended.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.errors.tool_error_category import ToolErrorCategory
from myrm_agent_harness.agent.middlewares.tooling import tool_executor
from myrm_agent_harness.agent.middlewares.tooling.tool_executor import execute_with_retry
from myrm_agent_harness.agent.streaming.event_handlers import _handle_tool_result
from myrm_agent_harness.agent.streaming.types import AgentEventType
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason, set_cancel_token
from myrm_agent_harness.utils.runtime.progress_sink import set_tool_progress_sink


def _request() -> MagicMock:
    request = MagicMock()
    request.tool_call = {"name": "web_fetch", "id": "tc_1"}
    return request


@pytest.fixture(autouse=True)
def _quiet_session_context() -> Iterator[None]:
    with (
        patch("myrm_agent_harness.agent.middlewares.tooling.tool_executor.get_event_logger", return_value=None),
        patch("myrm_agent_harness.agent.middlewares.tooling.tool_executor.get_terminal_errors", return_value=set()),
    ):
        yield


_TEST_GRACE_S = 1.0
_PRODUCTION_GRACE_S = tool_executor._STOP_GRACE_S


@pytest.fixture(autouse=True)
def _short_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production grace outlasts shell and browser cleanup; the tests only need it to be a known, short span."""
    monkeypatch.setattr(tool_executor, "_STOP_GRACE_S", _TEST_GRACE_S)


@pytest.fixture
def token() -> Iterator[CancellationToken]:
    request_token = CancellationToken("req-1")
    set_cancel_token(request_token)
    yield request_token
    set_cancel_token(None)


class _Handler:
    """Fails with ``failure`` the first time (stopping the request while it runs), then succeeds."""

    def __init__(
        self, failure: Exception, token: CancellationToken | None = None, stop_at: float | None = None
    ) -> None:
        self.failure = failure
        self.token = token
        self.stop_at = stop_at
        self.calls = 0

    async def __call__(self, _request: object) -> ToolMessage:
        self.calls += 1
        if self.calls == 1:
            if self.token is not None and self.stop_at is None:
                self.token.cancel()
            raise self.failure
        return ToolMessage(content="ok", name="web_fetch", tool_call_id="tc_1")


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TimeoutError(), ConnectionError("reset")], ids=["timeout", "transient-error"])
async def test_a_call_stopped_while_it_failed_is_not_retried(token: CancellationToken, failure: Exception) -> None:
    handler = _Handler(failure, token)

    result = await execute_with_retry(_request(), handler, "web_fetch", "tc_1", allowed_domains=None)

    assert handler.calls == 1
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert "cancelled" in str(result.content)


@pytest.mark.asyncio
async def test_a_stop_during_the_backoff_ends_the_wait_at_once(token: CancellationToken) -> None:
    handler = _Handler(ConnectionError("reset"), token, stop_at=0.2)

    async def stop_soon() -> None:
        await asyncio.sleep(0.2)
        token.cancel()

    stopper = asyncio.create_task(stop_soon())
    started = time.monotonic()
    result = await execute_with_retry(_request(), handler, "web_fetch", "tc_1", allowed_domains=None)
    await stopper

    # The backoff before a retry is at least one second.
    assert time.monotonic() - started < 0.9
    assert handler.calls == 1
    assert isinstance(result, ToolMessage)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_a_request_that_is_not_stopped_still_retries(token: CancellationToken) -> None:
    handler = _Handler(ConnectionError("reset"))

    with patch("myrm_agent_harness.agent.middlewares.tooling.tool_executor.asyncio.sleep") as sleep:
        sleep.return_value = None
        result = await execute_with_retry(_request(), handler, "web_fetch", "tc_1", allowed_domains=None)

    assert handler.calls == 2
    assert isinstance(result, ToolMessage)
    assert result.content == "ok"


class _SilentCall:
    """A call that only waits for its own result and never looks at the stop (a remote call with no cancel hook)."""

    def __init__(self, seconds: float = 5.0) -> None:
        self.seconds = seconds
        self.calls = 0
        self.cancelled = False

    async def __call__(self, _request: object) -> ToolMessage:
        self.calls += 1
        try:
            await asyncio.sleep(self.seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return ToolMessage(content="late", name="mcp_probe", tool_call_id="tc_1")


class _RecordingSink:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def emit(self, event: dict[str, object]) -> None:
        self.events.append(event)


async def _stop_after(
    token: CancellationToken, seconds: float, reason: CancelReason = CancelReason.USER_CANCELLED
) -> None:
    await asyncio.sleep(seconds)
    token.cancel(reason)


@pytest.mark.asyncio
async def test_a_stop_cancels_a_call_that_never_looks_at_it_and_reports_an_unknown_outcome(
    token: CancellationToken,
) -> None:
    call = _SilentCall()
    stopper = asyncio.create_task(_stop_after(token, 0.1))
    started = time.monotonic()

    result = await execute_with_retry(_request(), call, "mcp_probe", "tc_1", allowed_domains=None)
    await stopper

    # The poll interval plus the grace period, nowhere near the tool's own deadline.
    assert time.monotonic() - started < _TEST_GRACE_S + 1.5
    assert call.calls == 1, "a stopped call is not retried"
    assert call.cancelled, "the call itself is cancelled, not abandoned"
    assert isinstance(result, ToolMessage)
    assert result.status == "error"
    assert result.additional_kwargs["error_category"] == ToolErrorCategory.TOOL_CANCELLED
    assert "unknown" in str(result.content), "the model is told the outcome is unknown"

    # The person watching the run is shown what was cancelled and why, not the note that instructs the model.
    events = [event async for event in _handle_tool_result(result, "msg_1", None)]
    assert [event["error"] for event in events] == ["mcp_probe was cancelled (user_cancelled)"]


@pytest.mark.asyncio
async def test_a_call_that_answers_the_stop_within_the_grace_period_keeps_its_own_result(
    token: CancellationToken,
) -> None:
    async def cooperative(_request: object) -> ToolMessage:
        while not token.is_cancelled:
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.2)  # unwinding: kill the process, collect the partial output
        return ToolMessage(content="partial output", name="execute", tool_call_id="tc_1")

    stopper = asyncio.create_task(_stop_after(token, 0.1))
    result = await execute_with_retry(_request(), cooperative, "execute", "tc_1", allowed_domains=None)
    await stopper

    assert isinstance(result, ToolMessage)
    assert result.content == "partial output"


@pytest.mark.asyncio
async def test_a_cleanup_that_takes_seconds_is_not_cut_off_by_the_production_grace_period(
    token: CancellationToken, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second cancel arriving mid-cleanup abandons the cleanup (a wedged tab left unhealed, a process half killed)."""
    monkeypatch.setattr(tool_executor, "_STOP_GRACE_S", _PRODUCTION_GRACE_S)
    cleaned_up = False

    async def slow_cleanup(_request: object) -> ToolMessage:
        nonlocal cleaned_up
        while not token.is_cancelled:
            await asyncio.sleep(0.02)
        await asyncio.sleep(2.0)  # a shell that ignores SIGTERM, a wedged browser tab being healed
        cleaned_up = True
        return ToolMessage(content="partial output", name="execute", tool_call_id="tc_1")

    stopper = asyncio.create_task(_stop_after(token, 0.1))
    result = await execute_with_retry(_request(), slow_cleanup, "execute", "tc_1", allowed_domains=None)
    await stopper

    assert cleaned_up
    assert isinstance(result, ToolMessage)
    assert result.content == "partial output"


@pytest.mark.asyncio
async def test_a_stop_is_reported_to_the_stream_with_the_reason_it_had(token: CancellationToken) -> None:
    sink = _RecordingSink()
    set_tool_progress_sink(sink)
    try:
        stopper = asyncio.create_task(_stop_after(token, 0.05, CancelReason.DISCONNECT))
        await execute_with_retry(_request(), _SilentCall(), "mcp_probe", "tc_1", allowed_domains=None)
        await stopper
    finally:
        set_tool_progress_sink(None)

    cancelled = [event for event in sink.events if event["type"] == AgentEventType.TOOL_CANCELLED.value]
    assert len(cancelled) == 1
    data = cancelled[0]["data"]
    assert isinstance(data, dict)
    assert data["tool_name"] == "mcp_probe"
    assert data["cancel_reason"] == "session_ended"
    assert not [event for event in sink.events if event["type"] == AgentEventType.TOOL_TIMEOUT.value]


@pytest.mark.asyncio
async def test_a_call_without_a_request_token_is_not_cut_by_anything_but_its_deadline() -> None:
    set_cancel_token(None)

    async def quick(_request: object) -> ToolMessage:
        await asyncio.sleep(0.05)
        return ToolMessage(content="ok", name="mcp_probe", tool_call_id="tc_1")

    result = await execute_with_retry(_request(), quick, "mcp_probe", "tc_1", allowed_domains=None)

    assert isinstance(result, ToolMessage)
    assert result.content == "ok"
