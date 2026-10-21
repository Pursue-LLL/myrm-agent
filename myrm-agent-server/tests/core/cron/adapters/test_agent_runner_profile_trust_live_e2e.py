"""Live cron run bound to a profile carrying trusted desktop apps (Lane-C).

Proves the resolver -> adapter -> gate-params chain with a real DB profile
and a real model: the run must succeed and the trust entries must resolve.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.agent_runner import (
    AgentJobRunner,
    resolve_trusted_desktop_keys,
)
from app.database.dto import AgentCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.profile.profile_resolver import (
    get_agent_profile_resolver,
)

pytestmark = pytest.mark.e2e


async def test_live_cron_run_with_profile_trust() -> None:
    created = await AgentService.create_agent(
        AgentCreate(
            name="Trust Latch Profile E2E",
            system_prompt="You are a test agent.",
            trusted_desktop_apps=[{"name": "SAP GUI"}],
        )
    )
    try:
        get_agent_profile_resolver().invalidate(created.id)
        resolved = await get_agent_profile_resolver().resolve(created.id)
        assert resolved is not None
        assert resolved.trusted_desktop_apps == ({"name": "SAP GUI"},)
        assert resolve_trusted_desktop_keys(resolved.trusted_desktop_apps) == (
            "sap gui",
        )

        job = CronJob(  # type: ignore[arg-type]
            id="cron-trust-profile-ping",
            user_id="user-1",
            name="TrustProfilePing",
            job_type=JobType.AGENT,
            schedule=Schedule(kind=ScheduleKind.CRON, expr="0 2 * * *"),
            status=JobStatus.ACTIVE,
            prompt="Reply with exactly the word PONG and nothing else.",
            delivery=DeliveryConfig(channel="chat"),
            timeout_seconds=120,
            max_retries=0,
            agent_id=created.id,
        )
        result = await AgentJobRunner().run(job)
        assert result.success, f"cron run failed: {result.error}"
        assert result.output is not None and "PONG" in result.output
    finally:
        await AgentService.delete_agent(created.id)
