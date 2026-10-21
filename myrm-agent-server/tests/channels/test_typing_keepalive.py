"""Tests for MessageEffects typing keepalive."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.types import ChannelCapabilities


def _make_fx(keepalive_interval: float = 5.0) -> tuple[MessageEffects, MagicMock]:
    """Create MessageEffects with a mocked bus/channel."""
    bus = MagicMock()
    ch = MagicMock()
    ch.capabilities = ChannelCapabilities(typing_keepalive_interval=keepalive_interval)
    ch.start_typing = AsyncMock()
    ch.stop_typing = AsyncMock()
    bus.get_channel.return_value = ch
    fx = MessageEffects(bus)
    return fx, ch


class TestStartTypingKeepalive:
    def test_no_channel_noop(self) -> None:
        bus = MagicMock()
        bus.get_channel.return_value = None
        fx = MessageEffects(bus)
        fx.start_typing_keepalive("ch", "cid")
        assert len(fx._typing_keepalive_tasks) == 0

    def test_zero_interval_noop(self) -> None:
        fx, _ = _make_fx(keepalive_interval=0.0)
        fx.start_typing_keepalive("ch", "cid")
        assert len(fx._typing_keepalive_tasks) == 0

    @pytest.mark.asyncio
    async def test_creates_task(self) -> None:
        fx, _ = _make_fx(keepalive_interval=5.0)
        fx.start_typing_keepalive("ch", "cid")
        assert "ch:cid" in fx._typing_keepalive_tasks
        task = fx._typing_keepalive_tasks["ch:cid"]
        assert not task.done()
        task.cancel()

    @pytest.mark.asyncio
    async def test_idempotent_no_duplicate(self) -> None:
        fx, _ = _make_fx(keepalive_interval=5.0)
        fx.start_typing_keepalive("ch", "cid")
        first_task = fx._typing_keepalive_tasks["ch:cid"]
        fx.start_typing_keepalive("ch", "cid")
        assert fx._typing_keepalive_tasks["ch:cid"] is first_task
        first_task.cancel()

    @pytest.mark.asyncio
    async def test_keepalive_calls_start_typing(self) -> None:
        fx, ch = _make_fx(keepalive_interval=0.05)
        fx.start_typing_keepalive("ch", "cid")
        await asyncio.sleep(0.35)
        assert ch.start_typing.call_count >= 2
        await fx.stop_typing_keepalive("ch", "cid")


class TestStopTypingKeepalive:
    @pytest.mark.asyncio
    async def test_stops_running_task(self) -> None:
        fx, _ = _make_fx(keepalive_interval=0.05)
        fx.start_typing_keepalive("ch", "cid")
        assert "ch:cid" in fx._typing_keepalive_tasks
        await fx.stop_typing_keepalive("ch", "cid")
        assert "ch:cid" not in fx._typing_keepalive_tasks

    @pytest.mark.asyncio
    async def test_stop_nonexistent_noop(self) -> None:
        fx, _ = _make_fx()
        await fx.stop_typing_keepalive("ch", "no-such")

    @pytest.mark.asyncio
    async def test_keepalive_exception_does_not_crash(self) -> None:
        fx, ch = _make_fx(keepalive_interval=0.05)
        ch.start_typing = AsyncMock(side_effect=RuntimeError("network"))
        fx.start_typing_keepalive("ch", "cid")
        await asyncio.sleep(0.15)
        task = fx._typing_keepalive_tasks.get("ch:cid")
        assert task is not None and not task.done()
        await fx.stop_typing_keepalive("ch", "cid")
