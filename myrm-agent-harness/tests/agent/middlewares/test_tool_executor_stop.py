"""A stopped request is never retried: the retry would run again a call the user already stopped."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.middlewares.tooling.tool_executor import execute_with_retry
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, set_cancel_token


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
