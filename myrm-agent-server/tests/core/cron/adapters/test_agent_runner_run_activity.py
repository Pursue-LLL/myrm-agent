"""AgentJobRunner reports each run as in flight while it executes."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.cron.types import JobResult

from app.core.agent.run_activity import active_background_agent_runs
from app.core.cron.adapters.agent_runner import AgentJobRunner


@pytest.mark.asyncio
async def test_runner_counts_run_while_it_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[int] = []

    async def fake_run(self: AgentJobRunner, job: object, *, context: str) -> JobResult:
        observed.append(active_background_agent_runs())
        return JobResult(success=True)

    monkeypatch.setattr(AgentJobRunner, "_run_with_retries", fake_run)

    result = await AgentJobRunner().run(object(), context="")  # type: ignore[arg-type]

    assert result.success is True
    assert observed == [1]
    assert active_background_agent_runs() == 0


@pytest.mark.asyncio
async def test_runner_releases_count_when_run_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing_run(self: AgentJobRunner, job: object, *, context: str) -> JobResult:
        raise RuntimeError("agent crashed")

    monkeypatch.setattr(AgentJobRunner, "_run_with_retries", failing_run)

    with pytest.raises(RuntimeError):
        await AgentJobRunner().run(object(), context="")  # type: ignore[arg-type]

    assert active_background_agent_runs() == 0
