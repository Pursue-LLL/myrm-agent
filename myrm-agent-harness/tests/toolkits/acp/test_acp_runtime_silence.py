"""An ACP agent that goes quiet is reported as working; a missing ACP SDK ends the turn with a named error."""

from __future__ import annotations

import asyncio
import re
import sys

import pytest

from myrm_agent_harness.toolkits.acp.runtime._base import KEEPALIVE_SECONDS, working_status
from myrm_agent_harness.toolkits.acp.runtime.acp_callback import AcpCallbackHandler
from myrm_agent_harness.toolkits.acp.runtime.acp_runtime import AcpRuntime
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)


def _config() -> RuntimeConfig:
    return RuntimeConfig(backend_type="acp", command="agent", cwd="/tmp/ws")


def _is_working(event: RuntimeEvent) -> bool:
    return event.type is RuntimeEventType.STATUS_UPDATE and event.data["status"] == "working"


class TestSilentAgent:
    @pytest.mark.asyncio
    async def test_a_quiet_agent_keeps_reporting_how_long_the_turn_has_been_running(self) -> None:
        handler = AcpCallbackHandler(_config(), "acp-1")
        events = AcpRuntime._consume_events(handler, "s1", silence_seconds=0.05)

        quiet = [await asyncio.wait_for(anext(events), timeout=5) for _ in range(3)]

        assert all(_is_working(event) for event in quiet)
        assert all(re.fullmatch(r"\d+s", str(event.data["message"])) for event in quiet)
        await events.aclose()

    @pytest.mark.asyncio
    async def test_what_the_agent_says_comes_through_between_the_reports(self) -> None:
        handler = AcpCallbackHandler(_config(), "acp-1")
        events = AcpRuntime._consume_events(handler, "s1", silence_seconds=0.05)
        text = create_event(RuntimeEventType.TEXT_DELTA, "s1", content="hello")

        assert _is_working(await asyncio.wait_for(anext(events), timeout=5))
        handler.event_queue.put_nowait(text)
        assert await asyncio.wait_for(anext(events), timeout=5) is text
        handler.event_queue.put_nowait(None)

        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(events), timeout=5)

    @pytest.mark.asyncio
    async def test_an_agent_that_keeps_talking_is_never_reported_as_waiting(self) -> None:
        handler = AcpCallbackHandler(_config(), "acp-1")
        handler.event_queue.put_nowait(create_event(RuntimeEventType.TEXT_DELTA, "s1", content="a"))
        handler.event_queue.put_nowait(None)

        events = [event async for event in AcpRuntime._consume_events(handler, "s1")]

        assert [event.type for event in events] == [RuntimeEventType.TEXT_DELTA]


@pytest.mark.parametrize(
    ("seconds", "label"), [(0, "0s"), (5.9, "5s"), (60, "1m 00s"), (125, "2m 05s"), (3600, "60m 00s")]
)
def test_the_running_time_is_told_in_minutes_once_it_is_long(seconds: float, label: str) -> None:
    event = working_status("s1", seconds)

    assert event.data["status"] == "working"
    assert event.data["message"] == label


def test_the_silence_interval_is_the_one_the_server_watchdog_is_sized_for() -> None:
    assert KEEPALIVE_SECONDS == 15.0


class TestMissingSdk:
    @pytest.mark.asyncio
    async def test_a_host_without_the_acp_extra_gets_one_named_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(sys.modules, "acp", None)
        runtime = AcpRuntime("agent", _config())

        events = [event async for event in runtime.run_turn("hi", "s1")]

        errors = [event.data["error"] for event in events if event.type is RuntimeEventType.ERROR]
        assert len(errors) == 1
        assert isinstance(errors[0], AcpError)
        assert errors[0].code is AcpErrorCode.BACKEND_NOT_FOUND
        assert "myrm-agent-harness[acp]" in errors[0].message
        assert "ModuleNotFoundError" not in errors[0].message
        assert events[-1].type is RuntimeEventType.ERROR
