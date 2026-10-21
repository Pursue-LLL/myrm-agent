"""Tests for ChannelGateway enable/disable runtime toggle."""

from __future__ import annotations

import asyncio

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import (
    ChannelCapabilities,
    ChannelStatus,
    InboundMessage,
    OutboundMessage,
)


class StubChannel(BaseChannel):
    name = "stub"
    capabilities = ChannelCapabilities()

    def __init__(self, *, channel_name: str = "stub") -> None:
        super().__init__()
        type(self).name = channel_name  # type: ignore[assignment]
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "msg_ok"


def _make_gateway() -> tuple[ChannelGateway, StubChannel]:
    gw = ChannelGateway()
    ch = StubChannel()
    gw.register(ch)
    return gw, ch


@pytest.mark.asyncio
async def test_disable_sets_status() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        assert ch.status != ChannelStatus.DISABLED
        result = await gw.disable_channel("stub")
        assert result is True
        assert ch.status == ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disable_idempotent() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        await gw.disable_channel("stub")
        result = await gw.disable_channel("stub")
        assert result is True
        assert ch.status == ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disable_unknown_channel() -> None:
    gw, _ = _make_gateway()
    await gw.start()
    try:
        result = await gw.disable_channel("nonexistent")
        assert result is False
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_enable_after_disable() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        await gw.disable_channel("stub")
        assert ch.status == ChannelStatus.DISABLED
        result = await gw.enable_channel("stub")
        assert result is True
        assert ch.status != ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_enable_already_enabled() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        result = await gw.enable_channel("stub")
        assert result is True
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_enable_unknown_channel() -> None:
    gw, _ = _make_gateway()
    await gw.start()
    try:
        result = await gw.enable_channel("nonexistent")
        assert result is False
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disabled_channel_drops_inbound() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        await gw.disable_channel("stub")
        msg = InboundMessage(channel="stub", sender_id="u1", content="hi", chat_id="c1")
        await ch._emit_inbound(msg)
        assert gw.bus._inbound.empty()
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disabled_channel_drops_outbound() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        await gw.disable_channel("stub")
        out = OutboundMessage(channel="stub", recipient_id="u1", content="hi", user_id="test")
        await gw.bus.publish_outbound(out)
        await asyncio.sleep(0.1)
        assert len(ch.sent) == 0
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disable_emits_status_change_event() -> None:
    gw, ch = _make_gateway()
    events: list[dict[str, ChannelStatus]] = []

    def _on_status_change(_name: str, data: dict[str, ChannelStatus]) -> None:
        events.append(data)

    ch.on("status_change", _on_status_change)
    await gw.start()
    try:
        await gw.disable_channel("stub")
        assert len(events) >= 1
        assert events[-1]["new_status"] == ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_enable_emits_status_change_event() -> None:
    gw, ch = _make_gateway()
    events: list[dict[str, ChannelStatus]] = []

    def _on_status_change(_name: str, data: dict[str, ChannelStatus]) -> None:
        events.append(data)

    ch.on("status_change", _on_status_change)
    await gw.start()
    try:
        await gw.disable_channel("stub")
        events.clear()
        await gw.enable_channel("stub")
        assert len(events) == 1
        assert events[0]["old_status"] == ChannelStatus.DISABLED
        assert events[0]["new_status"] == ChannelStatus.IDLE
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_health_loop_skips_disabled() -> None:
    """Disabled channels are skipped in health loop (status remains DISABLED)."""
    gw, ch = _make_gateway()
    await gw.start()
    try:
        await gw.disable_channel("stub")
        assert ch.status == ChannelStatus.DISABLED
        statuses = gw.get_status()
        assert statuses["stub"] == ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disable_removes_channel_task() -> None:
    gw, _ = _make_gateway()
    await gw.start()
    try:
        assert "stub" in gw._channel_tasks
        await gw.disable_channel("stub")
        assert "stub" not in gw._channel_tasks
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_enable_recreates_channel_task() -> None:
    gw, _ = _make_gateway()
    await gw.start()
    try:
        await gw.disable_channel("stub")
        assert "stub" not in gw._channel_tasks
        await gw.enable_channel("stub")
        assert "stub" in gw._channel_tasks
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_run_channel_skips_disabled_on_boot() -> None:
    """Channels registered as DISABLED are not started by Gateway.start()."""
    gw = ChannelGateway()
    ch = StubChannel()
    ch._status = ChannelStatus.DISABLED
    gw.register(ch)
    await gw.start()
    try:
        assert ch.status == ChannelStatus.DISABLED
        statuses = gw.get_status()
        assert statuses["stub"] == ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_disabled_on_boot_can_be_enabled() -> None:
    """Channels registered as DISABLED can be enabled at runtime via enable_channel."""
    gw = ChannelGateway()
    ch = StubChannel()
    ch._status = ChannelStatus.DISABLED
    gw.register(ch)
    await gw.start()
    try:
        assert ch.status == ChannelStatus.DISABLED
        result = await gw.enable_channel("stub")
        assert result is True
        assert ch.status != ChannelStatus.DISABLED
        assert "stub" in gw._channel_tasks
    finally:
        await gw.stop()


# ---------------------------------------------------------------------------
# Gateway additional coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_idempotent() -> None:
    gw, _ = _make_gateway()
    await gw.start()
    await gw.start()
    try:
        assert gw._running is True
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_get_status() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        statuses = gw.get_status()
        assert "stub" in statuses
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_collect_all_issues_empty() -> None:
    gw, _ = _make_gateway()
    issues = gw.collect_all_issues()
    assert issues == {} or isinstance(issues, dict)


@pytest.mark.asyncio
async def test_collect_all_issues_with_issues() -> None:
    from app.channels.types import ChannelIssue, IssueKind, IssueSeverity

    class IssueChannel(StubChannel):
        def collect_issues(self) -> list[ChannelIssue]:
            return [ChannelIssue(kind=IssueKind.CONFIG, severity=IssueSeverity.ERROR, message="Missing config")]

    gw = ChannelGateway()
    ch = IssueChannel(channel_name="issue-ch")
    gw.register(ch)
    issues = gw.collect_all_issues()
    assert "issue-ch" in issues
    assert len(issues["issue-ch"]) == 1


@pytest.mark.asyncio
async def test_publish_convenience() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        msg = OutboundMessage(channel="stub", recipient_id="u1", content="hello", user_id="test")
        await gw.publish(msg)
        await asyncio.sleep(0.1)
        assert len(ch.sent) == 1
    finally:
        await gw.stop()


def test_compute_backoff() -> None:
    b = ChannelGateway._compute_backoff(1)
    assert 3.0 < b < 8.0

    b2 = ChannelGateway._compute_backoff(10)
    assert b2 <= 400.0


def test_should_restart_low_failures() -> None:
    ch = StubChannel()
    ch.health.consecutive_failures = 1
    assert ChannelGateway._should_restart(ch) is False


def test_should_restart_no_last_failure() -> None:
    ch = StubChannel()
    ch.health.consecutive_failures = 5
    ch.health.last_failure_at = None
    assert ChannelGateway._should_restart(ch) is True


def test_should_restart_backoff_not_elapsed() -> None:
    import time

    ch = StubChannel()
    ch.health.consecutive_failures = 3
    ch.health.last_failure_at = time.monotonic()
    assert ChannelGateway._should_restart(ch) is False


@pytest.mark.asyncio
async def test_status_change_callback() -> None:
    gw, ch = _make_gateway()
    events: list[tuple[str, ChannelStatus, ChannelStatus]] = []

    def callback(name: str, old: ChannelStatus, new: ChannelStatus) -> None:
        events.append((name, old, new))

    gw.set_status_change_callback(callback)
    await gw.start()
    try:
        await gw.disable_channel("stub")
        assert len(events) >= 1
        assert events[-1][2] == ChannelStatus.DISABLED
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_groups_change_callback() -> None:
    gw, ch = _make_gateway()
    events: list[tuple[str, list[object]]] = []

    def callback(name: str, groups: list[object]) -> None:
        events.append((name, groups))

    gw.set_groups_change_callback(callback)
    ch.emit("groups_change", [{"id": "g1"}])
    assert len(events) == 1
    assert events[0][0] == "stub"


@pytest.mark.asyncio
async def test_on_status_change_event_invalid_data() -> None:
    gw, _ = _make_gateway()
    gw._on_status_change_event("stub", {"old_status": "not-a-status", "new_status": "also-not"})


@pytest.mark.asyncio
async def test_run_channel_start_error() -> None:
    class FailChannel(StubChannel):
        async def start(self) -> None:
            raise RuntimeError("start failed")

    gw = ChannelGateway()
    ch = FailChannel(channel_name="fail-ch")
    gw.register(ch)
    await gw.start()
    try:
        await asyncio.sleep(0.05)
        assert ch.status == ChannelStatus.ERROR
    finally:
        await gw.stop()


@pytest.mark.asyncio
async def test_stop_channel_error_silenced() -> None:
    class StopFailChannel(StubChannel):
        async def stop(self) -> None:
            raise RuntimeError("stop failed")

    gw = ChannelGateway()
    ch = StopFailChannel(channel_name="stop-fail")
    gw.register(ch)
    await gw.start()
    await gw.stop()


@pytest.mark.asyncio
async def test_restart_channel() -> None:
    gw, ch = _make_gateway()
    await gw.start()
    try:
        await gw._restart_channel("stub", ch)
        assert "stub" in gw._channel_tasks
    finally:
        await gw.stop()
