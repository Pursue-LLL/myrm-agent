"""Tests for reconnect_loop exponential backoff utility."""

from __future__ import annotations

import asyncio

import pytest

from app.channels.reliability.reconnect import reconnect_loop
from app.channels.types import ChannelStatus


class TestReconnectLoop:
    @pytest.mark.asyncio
    async def test_stops_when_status_not_running(self) -> None:
        status = ChannelStatus.STOPPED
        call_count = 0

        async def connect() -> None:
            nonlocal call_count
            call_count += 1

        await reconnect_loop(connect, lambda: status, channel_name="test")
        assert call_count == 0

    @pytest.mark.asyncio
    async def test_calls_connect_fn_while_running(self) -> None:
        call_count = 0
        max_calls = 3

        async def connect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= max_calls:
                raise asyncio.CancelledError

        await reconnect_loop(
            connect,
            lambda: ChannelStatus.RUNNING,
            channel_name="test",
        )
        assert call_count == max_calls

    @pytest.mark.asyncio
    async def test_reconnects_on_exception(self) -> None:
        call_count = 0

        async def connect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("lost connection")
            raise asyncio.CancelledError

        await reconnect_loop(
            connect,
            lambda: ChannelStatus.RUNNING,
            channel_name="test",
            initial_backoff=0.01,
            max_backoff=0.05,
        )
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_resets_backoff_on_success(self) -> None:
        call_count = 0

        async def connect() -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return  # success — should reset backoff
            if call_count == 2:
                raise ConnectionError("fail")
            raise asyncio.CancelledError

        await reconnect_loop(
            connect,
            lambda: ChannelStatus.RUNNING,
            channel_name="test",
            initial_backoff=0.01,
            max_backoff=0.05,
        )
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exits_on_cancelled_error(self) -> None:
        call_count = 0

        async def connect() -> None:
            nonlocal call_count
            call_count += 1
            raise asyncio.CancelledError

        await reconnect_loop(connect, lambda: ChannelStatus.RUNNING, channel_name="test")
        assert call_count == 1
