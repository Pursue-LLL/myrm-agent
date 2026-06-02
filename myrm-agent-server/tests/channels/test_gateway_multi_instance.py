"""Tests for ChannelGateway multi-instance support (add/remove/list)."""

from __future__ import annotations

import asyncio

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    OutboundMessage,
)


def _make_stub(channel_name: str = "stub") -> BaseChannel:
    """Create a unique StubChannel subclass instance to avoid class-level name conflicts."""

    class _Stub(BaseChannel):
        name = channel_name
        capabilities = ChannelCapabilities()

        def __init__(self) -> None:
            super().__init__()
            self.sent: list[OutboundMessage] = []

        async def send(self, msg: OutboundMessage) -> str | None:
            self.sent.append(msg)
            return "msg_ok"

    return _Stub()


def _make_instance(channel_type: str, instance_id: str) -> BaseChannel:
    ch = _make_stub(f"{channel_type}_{instance_id}")
    ch.channel_type = channel_type
    return ch


# ── add_channel ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_add_channel_registers_and_starts() -> None:
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        inst = _make_instance("wechat", "abc123")
        name = await gw.add_channel(inst)
        assert name == "wechat_abc123"
        assert "wechat_abc123" in gw.bus.channels
        assert "wechat_abc123" in gw._channel_tasks
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_add_channel_respects_max_instances() -> None:
    gw = ChannelGateway()
    default = _make_stub("wechat")
    default.channel_type = "wechat"
    gw.register(default)
    await gw.start()
    try:
        for i in range(gw._MAX_INSTANCES_PER_TYPE - 1):
            inst = _make_instance("wechat", f"inst{i}")
            await gw.add_channel(inst)

        with pytest.raises(ValueError, match="limit"):
            inst = _make_instance("wechat", "overflow")
            await gw.add_channel(inst)
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_add_channel_duplicate_name_replaces() -> None:
    """Bus replaces existing channel when same name is re-registered."""
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        inst1 = _make_instance("wechat", "dup")
        await gw.add_channel(inst1)
        assert "wechat_dup" in gw.bus.channels

        inst2 = _make_instance("wechat", "dup")
        await gw.add_channel(inst2)
        assert gw.bus.channels["wechat_dup"] is inst2
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_add_channel_requires_running_gateway() -> None:
    gw = ChannelGateway()
    inst = _make_instance("wechat", "fail")
    with pytest.raises(RuntimeError, match="not running"):
        await gw.add_channel(inst)


# ── remove_channel ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_channel_stops_and_unregisters() -> None:
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        inst = _make_instance("wechat", "rm1")
        await gw.add_channel(inst)
        assert "wechat_rm1" in gw.bus.channels

        removed = await gw.remove_channel("wechat_rm1")
        assert removed is True
        assert "wechat_rm1" not in gw.bus.channels
        assert "wechat_rm1" not in gw._channel_tasks
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_remove_nonexistent_returns_false() -> None:
    gw = ChannelGateway()
    await gw.start()
    try:
        removed = await gw.remove_channel("nonexistent")
        assert removed is False
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_remove_default_channel() -> None:
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        removed = await gw.remove_channel("wechat")
        assert removed is True
        assert "wechat" not in gw.bus.channels
    finally:
        await gw.stop()


# ── list_instances ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_instances_returns_all() -> None:
    gw = ChannelGateway()
    default = _make_stub("wechat")
    default.channel_type = "wechat"
    gw.register(default)
    await gw.start()
    try:
        inst1 = _make_instance("wechat", "a1")
        inst2 = _make_instance("wechat", "b2")
        await gw.add_channel(inst1)
        await gw.add_channel(inst2)

        names = gw.list_instances("wechat")
        assert "wechat" in names
        assert "wechat_a1" in names
        assert "wechat_b2" in names
        assert len(names) == 3
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_list_instances_empty_type() -> None:
    gw = ChannelGateway()
    await gw.start()
    try:
        names = gw.list_instances("telegram")
        assert names == []
    finally:
        await gw.stop()


# ── _resolve_channel_type ────────────────────────────────────────


def test_resolve_channel_type_with_channel_type_attr() -> None:
    ch = _make_instance("wechat", "abc")
    assert ChannelGateway._resolve_channel_type(ch) == "wechat"


def test_resolve_channel_type_fallback_to_class_name() -> None:
    ch = _make_stub("telegram")
    result = ChannelGateway._resolve_channel_type(ch)
    assert result == "telegram"


# ── _count_instances ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_instances_includes_default() -> None:
    gw = ChannelGateway()
    default = _make_stub("wechat")
    default.channel_type = "wechat"
    gw.register(default)
    await gw.start()
    try:
        assert gw._count_instances("wechat") == 1
        inst = _make_instance("wechat", "x1")
        await gw.add_channel(inst)
        assert gw._count_instances("wechat") == 2
    finally:
        await gw.stop()


# ── Integration: add + send + remove ─────────────────────────────


@pytest.mark.asyncio
async def test_instance_receives_outbound_messages() -> None:
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        inst = _make_instance("wechat", "send1")
        await gw.add_channel(inst)

        msg = OutboundMessage(channel="wechat_send1", recipient_id="u1", content="hi", user_id="test")
        await gw.publish(msg)
        await asyncio.sleep(0.1)
        assert len(inst.sent) == 1  # type: ignore[attr-defined]
        assert inst.sent[0].content == "hi"  # type: ignore[attr-defined]
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_remove_then_add_same_id() -> None:
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        inst = _make_instance("wechat", "reuse")
        await gw.add_channel(inst)
        await gw.remove_channel("wechat_reuse")
        assert "wechat_reuse" not in gw.bus.channels

        inst2 = _make_instance("wechat", "reuse")
        name = await gw.add_channel(inst2)
        assert name == "wechat_reuse"
        assert "wechat_reuse" in gw.bus.channels
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_multiple_types_isolated() -> None:
    """Instances of different channel types don't interfere."""
    gw = ChannelGateway()
    wechat = _make_stub("wechat")
    wechat.channel_type = "wechat"
    telegram = _make_stub("telegram")
    telegram.channel_type = "telegram"
    gw.register(wechat)
    gw.register(telegram)
    await gw.start()
    try:
        await gw.add_channel(_make_instance("wechat", "w1"))
        await gw.add_channel(_make_instance("telegram", "t1"))

        wechat_instances = gw.list_instances("wechat")
        telegram_instances = gw.list_instances("telegram")
        assert "wechat_w1" in wechat_instances
        assert "telegram_t1" not in wechat_instances
        assert "telegram_t1" in telegram_instances
        assert "wechat_w1" not in telegram_instances
    finally:
        await gw.stop()


# ── list_channel_groups ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_channel_groups_empty() -> None:
    gw = ChannelGateway()
    gw.register(_make_stub("wechat"))
    await gw.start()
    try:
        groups = await gw.list_channel_groups()
        assert groups == []
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_list_channel_groups_with_provider() -> None:
    from app.channels.types import GroupInfo

    class GroupStub(BaseChannel):
        name = "group_ch"
        capabilities = ChannelCapabilities()

        async def send(self, msg: OutboundMessage) -> str | None:
            return None

        async def list_groups(self, *, force_refresh: bool = False) -> list[GroupInfo]:
            return [GroupInfo(jid="g1", name="Group 1", channel="")]

    gw = ChannelGateway()
    gw.register(GroupStub())
    await gw.start()
    try:
        groups = await gw.list_channel_groups()
        assert len(groups) == 1
        assert groups[0].jid == "g1"
        assert groups[0].channel == "group_ch"
    finally:
        await gw.stop()


# ── _run_channel idle path ───────────────────────────────────────


@pytest.mark.asyncio
async def test_run_channel_idle_status() -> None:
    """Channel that starts but stays IDLE (not configured)."""

    class IdleStub(BaseChannel):
        name = "idle_ch"
        capabilities = ChannelCapabilities()

        async def start(self) -> None:
            pass

        async def send(self, msg: OutboundMessage) -> str | None:
            return None

    gw = ChannelGateway()
    ch = IdleStub()
    gw.register(ch)
    await gw.start()
    try:
        await asyncio.sleep(0.05)
        assert ch.status == ChannelStatus.IDLE
    finally:
        await gw.stop()
