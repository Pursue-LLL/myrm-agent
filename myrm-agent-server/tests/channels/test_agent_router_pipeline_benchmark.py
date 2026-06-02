"""Wall-time regression guard for the mock AgentRouter pipeline (inbound → delivery).

Fully mocked channel and executor (no LLM, no network). Assertions bind measured
wall time to a loose ceiling only; they do not compare two implementations or assert speedup.
"""

from __future__ import annotations

import asyncio
import statistics
import time
from collections.abc import AsyncGenerator

import pytest

from app.channels.core.bus import MessageBus
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, OutboundMessage

from .test_progress_stream import (
    _NO_DEBOUNCE,
    _FakePairingStore,
    _FakePolicyProvider,
    _RecordingChannel,
)


class _DeliveryProbeChannel(_RecordingChannel):
    """Sets ``delivery_done`` when the final placeholder edit runs."""

    def __init__(self) -> None:
        super().__init__()
        self.delivery_done = asyncio.Event()

    async def edit_placeholder_message(
        self,
        chat_id: str,
        message_id: str,
        msg: OutboundMessage,
    ) -> None:
        await super().edit_placeholder_message(chat_id, message_id, msg)
        self.delivery_done.set()

    async def send(self, msg: OutboundMessage) -> str | None:
        result = await super().send(msg)
        self.delivery_done.set()
        return result


class _FinalOnlyExecutor:
    """Yields a single OutboundMessage (no ProgressUpdate, no StreamingText)."""

    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        **_kwargs: object,
    ) -> AsyncGenerator[OutboundMessage]:
        recipient = msg.chat_id or msg.sender_id
        yield OutboundMessage(
            channel=msg.channel,
            recipient_id=recipient,
            content="bench",
            user_id=user_id,
        )


def _make_inbound() -> InboundMessage:
    return InboundMessage(channel="test", sender_id="u1", content="hi", sent_at=time.time(), sent_timezone="UTC")


async def _one_round() -> float:
    bus = MessageBus()
    channel = _DeliveryProbeChannel()
    bus.register_channel(channel)
    router = AgentRouter(
        bus,
        _FakePairingStore(),
        _FinalOnlyExecutor(),
        _FakePolicyProvider(),
        session_gate_config=_NO_DEBOUNCE,
    )
    await bus.start()
    await router.start()
    channel.delivery_done.clear()
    t0 = time.perf_counter()
    await bus._handle_inbound(_make_inbound())
    await asyncio.wait_for(channel.delivery_done.wait(), timeout=15.0)
    elapsed = time.perf_counter() - t0
    await router.stop()
    await bus.stop()
    return elapsed


@pytest.mark.asyncio
@pytest.mark.benchmark
async def test_mock_pipeline_inbound_to_placeholder_edit_median_ceiling() -> None:
    """Median wall time per round stays below a loose ceiling (mock channel only).

    Guards against accidental blocking or deadlock on the happy path.
    """
    n = 12
    samples = [await _one_round() for _ in range(n)]
    med = statistics.median(samples)
    assert med < 5.0, f"median {med:.4f}s over {n} rounds (samples={samples!r})"
