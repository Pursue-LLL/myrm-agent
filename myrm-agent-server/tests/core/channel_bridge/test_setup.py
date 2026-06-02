from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


class _FakeGateway:
    def __init__(self) -> None:
        self.enable_kwargs: dict[str, object] | None = None
        self.started = False
        self.registered: list[object] = []

    def register(self, channel: object) -> None:
        self.registered.append(channel)

    def enable_bidirectional(self, **kwargs: object) -> None:
        self.enable_kwargs = kwargs

    def set_status_change_callback(self, callback: object) -> None:
        self.status_callback = callback

    def set_groups_change_callback(self, callback: object) -> None:
        self.groups_callback = callback

    def set_connection_change_callback(self, callback: object) -> None:
        self.connection_callback = callback

    async def start(self) -> None:
        self.started = True


class _FakeNotificationDispatcher:
    def __init__(self, event_bus: object) -> None:
        self.event_bus = event_bus
        self.started = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False


async def _empty_channels():
    if False:
        yield None


@pytest.mark.asyncio
async def test_start_channel_gateway_enables_core_router_in_cp_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.channel_bridge import setup as setup_module
    from app.services.event import app_event_bus as event_bus_module

    fake_gateway = _FakeGateway()

    monkeypatch.setattr(setup_module, "channel_gateway", fake_gateway)
    monkeypatch.setattr(setup_module, "create_all_channels", _empty_channels)
    monkeypatch.setattr(setup_module, "is_local_mode", lambda: False)
    monkeypatch.setattr(setup_module, "_restore_channel_instances", AsyncMock())
    monkeypatch.setattr(setup_module, "NotificationDispatcher", _FakeNotificationDispatcher)
    monkeypatch.setattr(event_bus_module, "get_event_bus", lambda: SimpleNamespace())

    await setup_module.start_channel_gateway()

    assert fake_gateway.started is True
    assert fake_gateway.enable_kwargs is not None
    assert fake_gateway.enable_kwargs["policy_provider"] is not None
    assert fake_gateway.enable_kwargs["topic_resolver"] is not None
    assert setup_module._notification_dispatcher is not None
