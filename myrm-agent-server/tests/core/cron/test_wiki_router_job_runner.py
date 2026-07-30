"""Tests for wiki router cron job runner."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

from app.core.cron.adapters.wiki_router_job_runner import (
    WIKI_MAINTAIN_COMMAND_PREFIX,
    WIKI_SOURCE_SYNC_COMMAND,
    WikiRouterJobRunner,
    parse_wiki_maintain_mode,
)
from app.services.wiki.maintain_schemas import WikiMaintainRunResult
from app.services.wiki.source_sync.schemas import WikiSourceSyncResult, WikiSourceSyncRunSummary


def _router_job(*, command: str) -> CronJob:
    return CronJob(
        id="job-1",
        user_id="default",
        name="Wiki router",
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 3 * * 0,6"),
        command=command,
        agent_id="agent-1",
    )


def test_parse_wiki_maintain_mode() -> None:
    assert parse_wiki_maintain_mode(f"{WIKI_MAINTAIN_COMMAND_PREFIX}:structural") == MaintainMode.STRUCTURAL
    assert parse_wiki_maintain_mode(f"{WIKI_MAINTAIN_COMMAND_PREFIX}:full") == MaintainMode.FULL
    assert parse_wiki_maintain_mode(WIKI_SOURCE_SYNC_COMMAND) is None


@pytest.mark.asyncio
async def test_run_source_sync_command() -> None:
    runner = WikiRouterJobRunner()
    summary = WikiSourceSyncRunSummary(
        results=[WikiSourceSyncResult(source="gmail", published=2)],
        total_published=2,
    )
    with patch(
        "app.services.wiki.source_sync.runner.run_wiki_source_sync",
        new=AsyncMock(return_value=summary),
    ):
        with patch(
            "app.services.agent.llm_access.get_optional_llm_for_user",
            new=AsyncMock(return_value=MagicMock()),
        ):
            result = await runner.run(_router_job(command=WIKI_SOURCE_SYNC_COMMAND))
    assert result.success is True
    assert "gmail" in result.output
    assert result.exit_code == 1


@pytest.mark.asyncio
async def test_run_maintain_structural_silent() -> None:
    runner = WikiRouterJobRunner()
    maintain_result = WikiMaintainRunResult(mode="structural", summary_text="[SILENT]")
    with patch(
        "app.services.wiki.maintain_runner.run_wiki_maintain_job",
        new=AsyncMock(return_value=maintain_result),
    ) as run_mock:
        with patch(
            "app.services.agent.llm_access.get_optional_llm_for_user",
            new=AsyncMock(return_value=MagicMock()),
        ):
            result = await runner.run(
                _router_job(command=f"{WIKI_MAINTAIN_COMMAND_PREFIX}:structural"),
            )
    run_mock.assert_awaited_once()
    assert run_mock.await_args.kwargs["mode"] == MaintainMode.STRUCTURAL
    assert result.success is True
    assert result.output == "[SILENT]"
    assert result.exit_code == 0
