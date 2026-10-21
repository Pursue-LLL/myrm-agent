"""Live cron adapter run with a real model (Lane-C).

Exercises the full AgentJobRunner path modified by the unattended desktop
trust latch: profile resolve -> tool intersect -> GeneralAgentParams
(including desktop_preapproved_trust_keys / desktop_unattended_fail_fast)
-> AgentFactory -> real LLM -> JobResult.
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

from app.core.cron.adapters.agent_runner import AgentJobRunner

pytestmark = pytest.mark.e2e


def _make_ping_job() -> CronJob:
    return CronJob(  # type: ignore[arg-type]
        id="cron-trust-latch-ping",
        user_id="user-1",
        name="TrustLatchPing",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 2 * * *"),
        status=JobStatus.ACTIVE,
        prompt="Reply with exactly the word PONG and nothing else.",
        delivery=DeliveryConfig(channel="chat"),
        timeout_seconds=120,
        max_retries=0,
    )


async def test_live_cron_run_with_trust_latch_params() -> None:
    runner = AgentJobRunner()
    result = await runner.run(_make_ping_job())
    assert result.success, f"cron run failed: {result.error}"
    assert result.output is not None and "PONG" in result.output
