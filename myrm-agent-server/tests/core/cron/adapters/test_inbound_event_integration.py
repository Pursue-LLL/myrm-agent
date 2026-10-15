"""Integration tests for inbound IM → cron event trigger (no mock on match/dispatch)."""

from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator

import pytest
from myrm_agent_harness.api.security import is_untrusted_ingress_active
from myrm_agent_harness.toolkits.cron import CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.triggers import EventTrigger, TriggerConfig
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, JobType, Schedule, ScheduleKind

from app.channels.protocols.pairing import DmPolicy, PairingRole, PairingStatus
from app.core.cron.adapters.inbound_event_dispatch import (
    dispatch_cron_event_for_inbound_message,
)


@pytest.fixture
async def cron_integration_env() -> AsyncIterator[tuple[CronManager, CronScheduler]]:
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
    cron_integration_env: tuple[CronManager, CronScheduler],
) -> None:
    manager, _scheduler = cron_integration_env

    await manager.create_job(
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
        untrusted=False,
    )

    assert count == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_non_matching_channel_does_not_dispatch(
    cron_integration_env: tuple[CronManager, CronScheduler],
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
        untrusted=False,
    )

    assert count == 0
    from app.core.cron.adapters.setup import get_cron_store

    runs = await get_cron_store().list_runs(job.id, limit=5)
    assert runs == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_channel_ingress_queues_single_router_dispatch(
    cron_integration_env: tuple[CronManager, CronScheduler],
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

    dispatch_calls: list[tuple[str, str, str, bool]] = []

    async def _record_dispatch(message: str, channel: str, user_id: str, *, untrusted: bool) -> int:
        dispatch_calls.append((message, channel, user_id, untrusted))
        return await dispatch_cron_event_for_inbound_message(message, channel, user_id, untrusted=untrusted)

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
    assert dispatch_calls[0] == ("server down", "feishu", "default", False)


class _FenceProbe:
    """Stands in for the agent runner: records whether the untrusted-ingress fence is active where the job runs."""

    def __init__(self) -> None:
        self.fence_seen: list[bool] = []

    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        self.fence_seen.append(is_untrusted_ingress_active())
        return JobResult(success=True, output="probe")


async def _create_fence_probe_job(manager: CronManager, scheduler: CronScheduler, channel: str) -> tuple[CronJob, _FenceProbe]:
    """An agent job fired by any "down" message on ``channel``, run by the probe so that no model is involved.

    The test database outlives a test, so every test owns its channel: no job left behind by another test can match.
    Exact timing (``stagger_ms=0``) keeps the scheduler from delaying a top-of-hour job by minutes.
    """
    probe = _FenceProbe()
    scheduler._runners[JobType.AGENT] = probe
    job = await manager.create_job(
        user_id="default",
        name=f"fence-probe-{channel}",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 0 * * *", stagger_ms=0),
        prompt="summarise the alert",
        triggers=TriggerConfig(events=(EventTrigger(pattern=r"down", channel=channel),)),
    )
    return job, probe


async def _wait_for_run(job_id: str, *, timeout: float = 10.0) -> None:
    """Wait until the triggered job's task has finished and recorded its run."""
    from app.core.cron.adapters.setup import get_cron_store

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not await get_cron_store().list_runs(job_id, limit=1):
        assert loop.time() < deadline, "the triggered job never recorded a run"
        await asyncio.sleep(0.05)


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("untrusted", [True, False], ids=["non-owner", "owner"])
async def test_job_task_runs_inside_the_fence_decided_at_dispatch(
    cron_integration_env: tuple[CronManager, CronScheduler],
    untrusted: bool,
) -> None:
    """The scheduler runs the job in a task of its own: the fence must reach that task and must not outlive dispatch."""
    manager, scheduler = cron_integration_env
    channel = f"probe{uuid.uuid4().hex[:8]}"
    job, probe = await _create_fence_probe_job(manager, scheduler, channel)

    count = await dispatch_cron_event_for_inbound_message("server down", channel, "default", untrusted=untrusted)
    await _wait_for_run(job.id)

    assert count == 1
    assert probe.fence_seen == [untrusted]
    assert not is_untrusted_ingress_active(), "the fence must not leak into the dispatching task"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("identity", "role", "untrusted"),
    [
        ("paired_member_chain-member", PairingRole.MEMBER, True),
        ("sandbox", PairingRole.ADMIN, False),
    ],
    ids=["paired-member", "owner"],
)
async def test_router_fences_the_job_a_non_owner_message_starts(
    cron_integration_env: tuple[CronManager, CronScheduler],
    identity: str,
    role: PairingRole,
    untrusted: bool,
) -> None:
    """One chain, no mock between the IM message and the job task: router verdict, dispatch, scheduler, runner."""
    from unittest.mock import AsyncMock, MagicMock, patch

    from app.channels.core.bus import MessageBus
    from app.channels.routing.router import AgentRouter
    from app.channels.routing.session_gate import SessionGateConfig
    from app.channels.types import InboundMessage

    manager, scheduler = cron_integration_env
    channel = f"chain{uuid.uuid4().hex[:8]}"
    job, probe = await _create_fence_probe_job(manager, scheduler, channel)

    pairing = MagicMock()
    pairing.resolve = AsyncMock(return_value=identity)
    pairing.get_pairing_detail = AsyncMock(return_value=(PairingStatus.ACTIVE, role, None))
    policy = MagicMock()
    policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
    bus = MessageBus()
    bus._ensure_queues()
    router = AgentRouter(
        bus=bus,
        pairing_store=pairing,
        agent_executor=AsyncMock(),
        policy_provider=policy,
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )

    await router.start()
    try:
        with patch.object(router._gate, "submit"):
            await bus._handle_inbound(
                InboundMessage(
                    channel=channel,
                    sender_id="chain-member",
                    chat_id="chain-member",
                    content="server down",
                    message_id="chain-1",
                    metadata={"message_id": "chain-1"},
                )
            )
            await _wait_for_run(job.id)
    finally:
        await router.stop()

    assert probe.fence_seen == [untrusted]
