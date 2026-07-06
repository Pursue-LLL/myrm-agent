"""Integration: EntitlementGuardedCronManager with real harness CronManager (no API mocks)."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.cron import CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import JobType, Schedule, ScheduleKind

from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager


class _NoopDelivery:
    async def deliver(self, job, result):  # noqa: ANN001
        return None


def _build_guarded_manager() -> EntitlementGuardedCronManager:
    store = InMemoryCronStore()
    scheduler = CronScheduler(
        store=store,
        runners={},
        delivery=_NoopDelivery(),
        config=CronConfig(),
    )
    inner = CronManager(store, scheduler, shell_enabled=True)
    return EntitlementGuardedCronManager(inner)


@pytest.mark.asyncio
async def test_create_job_succeeds_in_local_entitlement_mode() -> None:
    """Local deploy (no CP entitlements) must allow cron job creation end-to-end."""
    from unittest.mock import patch

    mgr = _build_guarded_manager()
    schedule = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=300_000)

    with patch(
        "app.platform_utils.deployment_capabilities.get_deployment_capabilities"
    ) as mock_caps:
        mock_caps.return_value.uses_cp_entitlements = False
        job = await mgr.create_job(
            user_id="default",
            name="integration-local",
            job_type=JobType.AGENT,
            schedule=schedule,
            prompt="ping",
        )

    assert job.name.startswith("integration-local")
    assert job.id


@pytest.mark.asyncio
async def test_create_job_blocked_when_sandbox_not_entitled() -> None:
    from unittest.mock import MagicMock, patch

    mgr = _build_guarded_manager()
    schedule = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=300_000)
    mock_ent = MagicMock()
    mock_ent.enable_cron = False
    mock_ent.max_cron_triggers = 0

    from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError

    with (
        patch(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities"
        ) as mock_caps,
        patch(
            "app.platform_utils.sandbox.entitlements.entitlement_guard.fetch_sandbox_entitlements",
            return_value=mock_ent,
        ),
        patch(
            "app.platform_utils.sandbox.entitlements.entitlement_guard.require_cron_entitlement",
            side_effect=EntitlementGuardError("blocked"),
        ),
    ):
        mock_caps.return_value.uses_cp_entitlements = True
        with pytest.raises(ValueError, match="blocked"):
            await mgr.create_job(
                user_id="default",
                name="integration-blocked",
                job_type=JobType.AGENT,
                schedule=schedule,
                prompt="ping",
            )


@pytest.mark.asyncio
async def test_create_job_blocked_at_max_cron_triggers() -> None:
    from unittest.mock import MagicMock, patch

    mgr = _build_guarded_manager()
    schedule = Schedule(kind=ScheduleKind.INTERVAL, interval_ms=300_000)
    mock_ent = MagicMock()
    mock_ent.enable_cron = True
    mock_ent.max_cron_triggers = 1

    with (
        patch(
            "app.platform_utils.deployment_capabilities.get_deployment_capabilities"
        ) as mock_caps,
        patch(
            "app.platform_utils.sandbox.entitlements.entitlement_guard.fetch_sandbox_entitlements",
            return_value=mock_ent,
        ),
    ):
        mock_caps.return_value.uses_cp_entitlements = True
        await mgr.create_job(
            user_id="default",
            name="first-job",
            job_type=JobType.AGENT,
            schedule=schedule,
            prompt="one",
        )
        with pytest.raises(ValueError, match="limit reached"):
            await mgr.create_job(
                user_id="default",
                name="second-job",
                job_type=JobType.AGENT,
                schedule=schedule,
                prompt="two",
            )
