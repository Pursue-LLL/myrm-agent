"""Tests for SessionGate.drain_unstarted: what a shutdown takes out of the gate before it cancels the running turns."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest

from app.channels.routing.session_gate import SessionGate, SessionGateConfig
from app.channels.types import InboundMessage
from tests.channels.session_gate_testkit import make_message


class TestDrainUnstarted:
    """A shutdown takes out what has not started a turn; the turns that run are left to be cancelled."""

    @staticmethod
    async def _running_gate(received: list[str], proceed: asyncio.Event) -> SessionGate:
        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg.content)
            if len(received) == 1:
                await proceed.wait()

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        gate.submit(make_message("running"))
        await asyncio.sleep(0.05)
        assert received == ["running"]
        return gate

    @pytest.mark.asyncio
    async def test_the_debounce_buffer_is_taken_and_its_timer_stopped(self) -> None:
        received: list[InboundMessage] = []

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)

        gate = SessionGate(SessionGateConfig(debounce_window_ms=100), on_ready=on_ready)
        gate.submit(make_message("a"))
        gate.submit(make_message("b"))

        assert [msg.content for msg in gate.drain_unstarted()] == ["a", "b"]
        await asyncio.sleep(0.2)
        assert received == []

    @pytest.mark.asyncio
    async def test_the_queue_behind_a_running_turn_is_taken_in_arrival_order(self) -> None:
        received: list[str] = []
        proceed = asyncio.Event()
        gate = await self._running_gate(received, proceed)
        gate.submit(make_message("queued-1"))
        gate.submit(make_message("queued-2"))

        assert [msg.content for msg in gate.drain_unstarted()] == ["queued-1", "queued-2"]
        assert gate.pending_count("telegram:user1") == 0
        proceed.set()

    @pytest.mark.asyncio
    async def test_ending_the_running_turn_starts_nothing_once_the_queue_is_taken(self) -> None:
        received: list[str] = []
        proceed = asyncio.Event()
        gate = await self._running_gate(received, proceed)
        gate.submit(make_message("queued"))
        gate.drain_unstarted()

        proceed.set()
        await asyncio.sleep(0.1)

        assert received == ["running"]
        assert gate.running_turn("telegram:user1") == 0

    @pytest.mark.asyncio
    async def test_an_answer_to_a_tool_approval_is_left_out(self) -> None:
        received: list[str] = []
        proceed = asyncio.Event()
        gate = await self._running_gate(received, proceed)
        gate.submit(dataclasses.replace(make_message("approve"), resume_value={"decisions": [{"type": "approve"}]}))
        gate.submit(make_message("queued"))

        assert [msg.content for msg in gate.drain_unstarted()] == ["queued"]
        proceed.set()

    @pytest.mark.asyncio
    async def test_every_session_is_drained(self) -> None:
        received: list[str] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg.content)
            await proceed.wait()

        gate = SessionGate(SessionGateConfig(debounce_window_ms=0), on_ready=on_ready)
        gate.submit(make_message("alice-running", sender_id="alice"))
        gate.submit(make_message("bob-running", sender_id="bob"))
        await asyncio.sleep(0.05)
        gate.submit(make_message("alice-queued", sender_id="alice"))
        gate.submit(make_message("bob-queued", sender_id="bob"))

        assert sorted(msg.content for msg in gate.drain_unstarted()) == ["alice-queued", "bob-queued"]
        proceed.set()

    def test_an_idle_gate_has_nothing_to_drain(self) -> None:
        async def on_ready(msg: InboundMessage) -> None:
            pass

        assert SessionGate(SessionGateConfig(), on_ready=on_ready).drain_unstarted() == []
