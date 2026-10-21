"""Tests for ChannelActivity tracking."""

from __future__ import annotations

import time

from app.channels.core.base import BaseChannel
from app.channels.types import (
    ChannelActivity,
    OutboundMessage,
)


class TestChannelActivity:
    def test_initial_state(self) -> None:
        a = ChannelActivity()
        assert a.last_inbound_at is None
        assert a.last_outbound_at is None
        assert a.last_active_at is None

    def test_record_inbound(self) -> None:
        a = ChannelActivity()
        before = time.time()
        a.record_inbound()
        after = time.time()
        assert a.last_inbound_at is not None
        assert before <= a.last_inbound_at <= after

    def test_record_outbound(self) -> None:
        a = ChannelActivity()
        before = time.time()
        a.record_outbound()
        after = time.time()
        assert a.last_outbound_at is not None
        assert before <= a.last_outbound_at <= after

    def test_last_active_at_inbound_only(self) -> None:
        a = ChannelActivity()
        a.record_inbound()
        assert a.last_active_at == a.last_inbound_at

    def test_last_active_at_outbound_only(self) -> None:
        a = ChannelActivity()
        a.record_outbound()
        assert a.last_active_at == a.last_outbound_at

    def test_last_active_at_picks_max(self) -> None:
        a = ChannelActivity()
        a.record_inbound()
        time.sleep(0.01)
        a.record_outbound()
        assert a.last_active_at == a.last_outbound_at
        assert a.last_active_at is not None
        assert a.last_inbound_at is not None
        assert a.last_active_at > a.last_inbound_at


class DummyChannel(BaseChannel):
    name = "dummy"

    async def send(self, msg: OutboundMessage) -> str | None:
        pass


class TestBaseChannelActivity:
    def test_has_activity_attribute(self) -> None:
        ch = DummyChannel()
        assert isinstance(ch.activity, ChannelActivity)

    def test_activity_independent_per_instance(self) -> None:
        ch1 = DummyChannel()
        ch2 = DummyChannel()
        ch1.activity.record_inbound()
        assert ch1.activity.last_inbound_at is not None
        assert ch2.activity.last_inbound_at is None
