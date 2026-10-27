"""A failing disk write must degrade a durable send to an unpersisted one, never block or drop it."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.reliability import durable_outbound
from app.channels.reliability.durable_outbound import DurableOutboundGate
from app.channels.types import ChannelCapabilities, OutboundMessage

_GATE_LOGGER = "app.channels.reliability.durable_outbound"


class _RecordingChannel(BaseChannel):
    name = "feishu"
    capabilities = ChannelCapabilities()

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "platform_msg_1"


def _outbound(content: str = "hello") -> OutboundMessage:
    return OutboundMessage(channel="feishu", recipient_id="user_1", content=content, user_id="u1")


@pytest.fixture
def full_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(durable_outbound, "save_delivery", _raise)


@pytest.mark.asyncio
async def test_prepare_enqueue_returns_unpersisted_message_and_warns(
    tmp_path: Path, full_disk: None, caplog: pytest.LogCaptureFixture
) -> None:
    gate = DurableOutboundGate(tmp_path)
    original = _outbound()

    with caplog.at_level(logging.WARNING, logger=_GATE_LOGGER):
        msg = await gate.prepare_enqueue(original)

    assert msg is original
    assert gate.get_delivery_id(msg) is None
    assert not gate.retains(msg)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "persist failed" in r.getMessage()]
    assert len(warnings) == 1
    assert warnings[0].exc_info is not None


@pytest.mark.asyncio
async def test_unpersisted_message_makes_mark_attempting_and_ack_noops(tmp_path: Path, full_disk: None) -> None:
    gate = DurableOutboundGate(tmp_path)
    msg = await gate.prepare_enqueue(_outbound())

    await gate.mark_attempting(msg)
    await gate.ack(msg)


@pytest.mark.asyncio
async def test_persist_direct_send_degrades_the_same_way(tmp_path: Path, full_disk: None) -> None:
    gate = DurableOutboundGate(tmp_path)
    original = _outbound()

    assert await gate.persist_direct_send(original) is original


@pytest.mark.asyncio
async def test_publish_outbound_still_delivers_when_persist_fails(tmp_path: Path, full_disk: None) -> None:
    bus = MessageBus(dlq_dir=tmp_path)
    ch = _RecordingChannel()
    bus.register_channel(ch)
    await bus.start()

    try:
        await bus.publish_outbound(_outbound("must still arrive"))
        await asyncio.sleep(0.3)

        assert [m.content for m in ch.sent] == ["must still arrive"]
        assert DurableOutboundGate.get_delivery_id(ch.sent[0]) is None
    finally:
        await bus.stop()


@pytest.mark.asyncio
async def test_cancellation_during_persist_is_not_swallowed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _cancel(*_args: object, **_kwargs: object) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(durable_outbound, "save_delivery", _cancel)
    gate = DurableOutboundGate(tmp_path)

    with pytest.raises(asyncio.CancelledError):
        await gate.prepare_enqueue(_outbound())
