"""Tests for the SessionGate busy-ack callback.

Covers when the queued and queue-full notices fire, how their separate per-session 30 s clocks
behave (debounce, restart after the session drains, `clear`), and that a missing or failing
callback never disturbs the queue.
"""

from __future__ import annotations

import asyncio

import pytest

from app.channels.routing.session_gate import SessionGate, SessionGateConfig
from app.channels.types import InboundMessage
from tests.channels.session_gate_testkit import make_message


class TestBusyAck:
    @pytest.mark.asyncio
    async def test_busy_ack_fires_on_queue(self) -> None:
        """When a message is queued while active, on_busy_ack fires with correct position."""
        received: list[InboundMessage] = []
        ack_calls: list[tuple[InboundMessage, int, int]] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append((msg, position, max_pending))

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=10),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)
        assert len(received) == 1

        gate.submit(make_message("queued"))
        await asyncio.sleep(0.05)

        assert len(ack_calls) == 1
        assert ack_calls[0][1] == 1
        assert ack_calls[0][2] == 10

        proceed.set()
        await asyncio.sleep(0.15)

    @pytest.mark.asyncio
    async def test_busy_ack_fires_on_queue_full(self) -> None:
        """A full queue is reported with position=-1, right after the queued notice that filled it."""
        received: list[InboundMessage] = []
        ack_calls: list[tuple[InboundMessage, int, int]] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append((msg, position, max_pending))

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=1),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)

        gate.submit(make_message("fills queue"))
        await asyncio.sleep(0.05)
        assert len(ack_calls) == 1
        assert ack_calls[0][1] == 1

        gate.submit(make_message("dropped"))
        await asyncio.sleep(0.05)
        assert len(ack_calls) == 2
        assert ack_calls[1][1] == -1
        assert ack_calls[1][2] == 1

        proceed.set()
        await asyncio.sleep(0.15)

    @pytest.mark.asyncio
    async def test_busy_ack_debounce_suppresses_rapid_acks(self) -> None:
        """Within the debounce window (30s), only the first ack fires."""
        received: list[InboundMessage] = []
        ack_calls: list[tuple[InboundMessage, int, int]] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append((msg, position, max_pending))

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=10),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)

        gate.submit(make_message("q1"))
        gate.submit(make_message("q2"))
        gate.submit(make_message("q3"))
        await asyncio.sleep(0.05)

        assert len(ack_calls) == 1

        proceed.set()
        await asyncio.sleep(0.15)

    @pytest.mark.asyncio
    async def test_busy_ack_independent_per_session(self) -> None:
        """Different session keys have independent debounce timers."""
        ack_calls: list[tuple[str, int]] = []
        proceeds: dict[str, asyncio.Event] = {"alice": asyncio.Event(), "bob": asyncio.Event()}

        async def on_ready(msg: InboundMessage) -> None:
            key = msg.sender_id
            if key in proceeds:
                await proceeds[key].wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append((msg.sender_id, position))

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=10),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )

        gate.submit(make_message("a1", sender_id="alice"))
        gate.submit(make_message("b1", sender_id="bob"))
        await asyncio.sleep(0.1)

        gate.submit(make_message("a-queued", sender_id="alice"))
        gate.submit(make_message("b-queued", sender_id="bob"))
        await asyncio.sleep(0.05)

        senders = {s for s, _ in ack_calls}
        assert senders == {"alice", "bob"}

        proceeds["alice"].set()
        proceeds["bob"].set()
        await asyncio.sleep(0.15)

    @pytest.mark.asyncio
    async def test_no_busy_ack_without_callback(self) -> None:
        """When on_busy_ack is None, queuing works normally without errors."""
        received: list[InboundMessage] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30),
            on_ready=on_ready,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)
        assert len(received) == 1

        gate.submit(make_message("queued"))
        await asyncio.sleep(0.05)
        assert gate.pending_count("telegram:user1") == 1

        proceed.set()
        await asyncio.sleep(0.15)
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_busy_ack_callback_exception_does_not_break_queue(self) -> None:
        """If on_busy_ack raises, the message is still queued correctly."""
        received: list[InboundMessage] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            received.append(msg)
            if len(received) == 1:
                await proceed.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            raise RuntimeError("ack send failure")

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=5),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)

        gate.submit(make_message("queued"))
        await asyncio.sleep(0.1)

        assert gate.pending_count("telegram:user1") == 1

        proceed.set()
        await asyncio.sleep(0.15)
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_clear_drops_session_state(self) -> None:
        """clear() drops every session together with its queue and notice clocks."""
        ack_calls: list[int] = []
        proceed = asyncio.Event()

        async def on_ready(msg: InboundMessage) -> None:
            await proceed.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append(position)

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=5),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)

        gate.submit(make_message("queued"))
        await asyncio.sleep(0.05)
        assert gate.pending_count("telegram:user1") == 1

        gate.clear()
        assert len(gate._sessions) == 0

    @pytest.mark.asyncio
    async def test_notice_clock_restarts_when_session_drains(self) -> None:
        """A session that drained starts its next busy period with fresh notice clocks."""
        release = asyncio.Event()
        ack_calls: list[int] = []

        async def on_ready(msg: InboundMessage) -> None:
            if msg.content in {"first", "again"}:
                await release.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append(position)

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=5),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)
        gate.submit(make_message("queued"))
        await asyncio.sleep(0.05)
        assert ack_calls == [1]

        release.set()
        await asyncio.sleep(0.3)
        assert not gate.is_busy(make_message())
        assert len(gate._sessions) == 0

        release.clear()
        gate.submit(make_message("again"))
        await asyncio.sleep(0.1)
        gate.submit(make_message("queued again"))
        await asyncio.sleep(0.05)
        assert ack_calls == [1, 1]

        release.set()
        await asyncio.sleep(0.15)

    @pytest.mark.asyncio
    async def test_queue_full_notice_follows_queued_notice_in_one_busy_period(self) -> None:
        """Messages that overflow a queue filled within 30 s of its queued notice still get the queue-full notice."""
        release = asyncio.Event()
        ack_calls: list[tuple[int, int]] = []

        async def on_ready(msg: InboundMessage) -> None:
            if msg.content == "first":
                await release.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append((position, max_pending))

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=10),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)
        for index in range(12):
            gate.submit(make_message(f"burst {index}"))
        await asyncio.sleep(0.05)

        assert gate.pending_count("telegram:user1") == 10
        assert ack_calls == [(1, 10), (-1, 10)]

        release.set()
        await asyncio.sleep(0.15)

    @pytest.mark.asyncio
    async def test_queue_full_notice_is_debounced_per_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Repeated overflow does not repeat the queue-full notice inside the window, and does again after it."""
        monkeypatch.setattr("app.channels.routing.session_gate._BUSY_ACK_DEBOUNCE_S", 0.2)
        release = asyncio.Event()
        ack_calls: list[int] = []

        async def on_ready(msg: InboundMessage) -> None:
            if msg.content == "first":
                await release.wait()

        async def on_busy_ack(msg: InboundMessage, position: int, max_pending: int) -> None:
            ack_calls.append(position)

        gate = SessionGate(
            SessionGateConfig(debounce_window_ms=30, max_pending_per_session=1),
            on_ready=on_ready,
            on_busy_ack=on_busy_ack,
        )
        gate.submit(make_message("first"))
        await asyncio.sleep(0.1)
        gate.submit(make_message("fills queue"))
        gate.submit(make_message("dropped 1"))
        gate.submit(make_message("dropped 2"))
        await asyncio.sleep(0.05)
        assert ack_calls == [1, -1]

        await asyncio.sleep(0.25)
        gate.submit(make_message("dropped 3"))
        await asyncio.sleep(0.05)
        assert ack_calls == [1, -1, -1]

        release.set()
        await asyncio.sleep(0.15)
