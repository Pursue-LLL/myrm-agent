"""The guards of the bounded stop that need no real agent: who is never signalled, how long a close can take."""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

import pytest

from myrm_agent_harness.toolkits.acp.runtime.acp import stalled_agent
from myrm_agent_harness.toolkits.code_execution.session import process_tree

if TYPE_CHECKING:
    from asyncio.subprocess import Process

    from acp import ClientSideConnection


@dataclass
class _FakeProcess:
    returncode: int | None


class _HangingTransport:
    """A transport whose exit never returns, as when the agent still holds the write it never read."""

    def __init__(self) -> None:
        self.abandoned = False

    async def __aexit__(self, *_exc: object) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.abandoned = True
            raise


@pytest.fixture
def signalled(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """The processes whose tree the stop was asked to end, with no process touched."""
    ended: list[object] = []

    async def record(process: object, _is_win: bool, _grace: float) -> None:
        ended.append(process)

    monkeypatch.setattr(process_tree, "kill_process_tree", record)
    return ended


class TestEndAgent:
    @pytest.mark.asyncio
    async def test_a_running_agent_is_ended_with_its_tools(self, signalled: list[object]) -> None:
        agent = _FakeProcess(returncode=None)

        await stalled_agent.end_agent(cast("Process", agent))

        assert signalled == [agent]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("agent", [None, _FakeProcess(returncode=0), _FakeProcess(returncode=-9)])
    async def test_an_agent_that_is_gone_is_never_signalled(
        self, signalled: list[object], agent: _FakeProcess | None
    ) -> None:
        """A reaped agent's PID may belong to an unrelated process by now."""
        await stalled_agent.end_agent(cast("Process | None", agent))

        assert signalled == []


class TestLeaveTransport:
    @pytest.mark.asyncio
    async def test_a_transport_that_never_lets_go_is_abandoned_after_two_bounds(
        self, signalled: list[object], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        monkeypatch.setattr(stalled_agent, "STALLED_AGENT_TIMEOUT_SECONDS", 0.05)
        transport = _HangingTransport()
        agent = _FakeProcess(returncode=None)
        started = time.monotonic()

        with caplog.at_level(logging.WARNING, logger=stalled_agent.logger.name):
            await stalled_agent.leave_transport(
                cast("AbstractAsyncContextManager[tuple[ClientSideConnection, Process]]", transport),
                cast("Process", agent),
                "stuck",
            )
        await asyncio.sleep(0.05)

        assert time.monotonic() - started < 2
        assert signalled == [agent]
        assert transport.abandoned
        assert any(r.getMessage().startswith("acp_transport_exit_timeout name=stuck") for r in caplog.records)
