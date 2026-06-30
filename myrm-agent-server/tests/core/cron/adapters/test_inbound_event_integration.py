"""Integration tests for inbound IM → cron event trigger (no mock on match/dispatch)."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

import pytest
from myrm_agent_harness.toolkits.cron.triggers import EventTrigger, TriggerConfig
from myrm_agent_harness.toolkits.cron.types import JobType, Schedule, ScheduleKind

from app.core.cron.adapters.inbound_event_dispatch import (
    dispatch_cron_event_for_inbound_message,
)


@pytest.fixture
async def cron_integration_env() -> AsyncIterator[tuple[object, object]]:
    import app.core.cron.adapters.setup as cron_setup

    cron_setup._scheduler = None
    cron_setup._manager = None
    cron_setup._store = None

    manager = cron_setup.get_cron_manager()
    scheduler = cron_setup.get_cron_scheduler()
    try:
        yield manager, scheduler
    finally:
        cron_setup._scheduler = None
        cron_setup._manager = None
        cron_setup._store = None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_sqlalchemy_provider_dispatches_matching_event_job(
    cron_integration_env: tuple[object, object],
) -> None:
    manager, _scheduler = cron_integration_env

    job = await manager.create_job(
        user_id="default",
        name="feishu-alert",
        job_type=JobType.SHELL,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 0 * * *"),
        command="echo triggered",
        triggers=TriggerConfig(
            events=(EventTrigger(pattern=r"server.*down", channel="feishu"),),
        ),
    )

    count = await dispatch_cron_event_for_inbound_message(
        "production server-3 down",
        "feishu",
        "default",
    )

    assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_matching_channel_does_not_dispatch(
    cron_integration_env: tuple[object, object],
) -> None:
    manager, _scheduler = cron_integration_env

    job = await manager.create_job(
        user_id="default",
        name="telegram-only",
        job_type=JobType.SHELL,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 0 * * *"),
        command="echo nope",
        triggers=TriggerConfig(
            events=(EventTrigger(pattern=r"alert", channel="telegram"),),
        ),
    )

    count = await dispatch_cron_event_for_inbound_message(
        "alert here",
        "feishu",
        "default",
    )

    assert count == 0
    from app.core.cron.adapters.setup import get_cron_store

    runs = await get_cron_store().list_runs(job.id, limit=5)
    assert runs == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_channel_ingress_queues_single_router_dispatch(
    cron_integration_env: tuple[object, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingress enqueues once; router performs exactly one cron dispatch."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.api.channels.channel_ingress import (
        ChannelIngressRequest,
        ResolvedChannelIdentityRequest,
        ingest_channel_message,
    )
    from app.channels.core.bus import MessageBus
    from app.channels.routing.router import AgentRouter
    from app.channels.routing.session_gate import SessionGateConfig
    from app.core import channel_bridge as channels_module

    manager, _scheduler = cron_integration_env
    await manager.create_job(
        user_id="default",
        name="cp-alert",
        job_type=JobType.SHELL,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 0 * * *"),
        command="echo cp",
        triggers=TriggerConfig(
            events=(EventTrigger(pattern=r"down", channel="feishu"),),
        ),
    )

    dispatch_calls: list[tuple[str, str, str]] = []

    async def _record_dispatch(message: str, channel: str, user_id: str) -> int:
        dispatch_calls.append((message, channel, user_id))
        return await dispatch_cron_event_for_inbound_message(message, channel, user_id)

    bus = MessageBus()
    bus._ensure_queues()
    router = AgentRouter(
        bus=bus,
        pairing_store=MagicMock(),
        agent_executor=AsyncMock(),
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )
    gateway = SimpleNamespace(bus=bus, _router=router)
    monkeypatch.setattr(channels_module, "channel_gateway", gateway)
    monkeypatch.setattr(
        "app.channels.routing.router.dispatch_cron_event_for_inbound_message",
        _record_dispatch,
    )

    await router.start()
    try:
        with patch.object(router._gate, "submit"):
            body = ChannelIngressRequest(
                message_id="int-msg-1",
                content="server down",
                channel_type="feishu",
                chat_type="private",
                chat_id="chat-int",
                channel_user_id="owner-int",
                timestamp=1710000100.0,
                resolved_identity=ResolvedChannelIdentityRequest(
                    platform_user_id="default",
                    sandbox_owner_id="default",
                    channel_id="feishu",
                    channel_user_id="owner-int",
                    conversation_id="feishu:private:chat-int",
                    task_id="feishu:private:chat-int",
                ),
            )
            result = await ingest_channel_message(body)
            assert result == {"status": "queued"}
            await asyncio.sleep(0.2)
    finally:
        await router.stop()

    assert len(dispatch_calls) == 1
    assert dispatch_calls[0] == ("server down", "feishu", "default")
