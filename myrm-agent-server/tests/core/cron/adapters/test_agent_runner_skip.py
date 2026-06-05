"""Unit tests for AgentJobRunner no-content skip logic.

Validates that heartbeat jobs skip the LLM call when the situation report
has no actionable content, and proceed normally when content exists.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.heartbeat import HEARTBEAT_JOB_NAME
from myrm_agent_harness.toolkits.cron.situation import SituationReportBuilder
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.agent_runner import AgentJobRunner

_BUDGET_MODULE = "app.services.budget.enforcer.should_block_execution"


def _make_heartbeat_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "hb-1",
        "user_id": "user-1",
        "name": HEARTBEAT_JOB_NAME,
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="*/30 * * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Check system status and report any anomalies.",
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


def _make_regular_job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "cron-1",
        "user_id": "user-1",
        "name": "Daily Report",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Generate daily report.",
        "delivery": DeliveryConfig(channel="chat"),
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


class TestInjectSituationReport:
    """Tests for _inject_situation_report method."""

    @pytest.mark.asyncio
    async def test_empty_report_returns_no_content(self) -> None:
        builder = AsyncMock(spec=SituationReportBuilder)
        builder.build = AsyncMock(return_value=None)
        runner = AgentJobRunner(situation_builder=builder)

        prompt, has_content = await runner._inject_situation_report(_make_heartbeat_job(), "original prompt")
        assert not has_content
        assert prompt == "original prompt"

    @pytest.mark.asyncio
    async def test_empty_string_report_returns_no_content(self) -> None:
        builder = AsyncMock(spec=SituationReportBuilder)
        builder.build = AsyncMock(return_value="")
        runner = AgentJobRunner(situation_builder=builder)

        prompt, has_content = await runner._inject_situation_report(_make_heartbeat_job(), "original prompt")
        assert not has_content

    @pytest.mark.asyncio
    async def test_report_with_content_returns_true(self) -> None:
        builder = AsyncMock(spec=SituationReportBuilder)
        builder.build = AsyncMock(return_value="## Pending Commitments\n- Review PR #42")
        runner = AgentJobRunner(situation_builder=builder)

        prompt, has_content = await runner._inject_situation_report(_make_heartbeat_job(), "original prompt")
        assert has_content
        assert "<situation_report>" in prompt
        assert "Pending Commitments" in prompt
        assert "original prompt" in prompt

    @pytest.mark.asyncio
    async def test_build_exception_returns_true_for_safety(self) -> None:
        builder = AsyncMock(spec=SituationReportBuilder)
        builder.build = AsyncMock(side_effect=RuntimeError("DB error"))
        runner = AgentJobRunner(situation_builder=builder)

        prompt, has_content = await runner._inject_situation_report(_make_heartbeat_job(), "original prompt")
        assert has_content
        assert prompt == "original prompt"


class TestHeartbeatSkipLogic:
    """Tests for the no-content skip path in _run_once."""

    @pytest.mark.asyncio
    async def test_heartbeat_no_content_returns_skipped(self) -> None:
        builder = AsyncMock(spec=SituationReportBuilder)
        builder.build = AsyncMock(return_value=None)
        runner = AgentJobRunner(situation_builder=builder)

        job = _make_heartbeat_job()
        with patch(
            _BUDGET_MODULE,
            new_callable=AsyncMock,
            return_value=False,
        ):
            result = await runner._run_once(job)

        assert result.success is True
        assert result.skipped is True
        assert result.skip_reason == "no-content"

    @pytest.mark.asyncio
    async def test_regular_job_bypasses_inject(self) -> None:
        """Non-heartbeat jobs never call _inject_situation_report."""
        builder = AsyncMock(spec=SituationReportBuilder)
        runner = AgentJobRunner(situation_builder=builder)
        job = _make_regular_job()

        with (
            patch(
                _BUDGET_MODULE,
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                runner,
                "_inject_situation_report",
                new_callable=AsyncMock,
            ) as mock_inject,
        ):
            mock_inject.return_value = ("irrelevant", True)
            # _run_once will proceed past inject to agent creation which we
            # don't need — the assertion is that inject is never called
            try:
                await runner._run_once(job)
            except Exception:
                pass

        mock_inject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_builder_bypasses_inject(self) -> None:
        """Without SituationReportBuilder, heartbeat still runs (no skip)."""
        runner = AgentJobRunner(situation_builder=None)
        job = _make_heartbeat_job()

        with (
            patch(
                _BUDGET_MODULE,
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                runner,
                "_inject_situation_report",
                new_callable=AsyncMock,
            ) as mock_inject,
        ):
            try:
                await runner._run_once(job)
            except Exception:
                pass

        mock_inject.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_heartbeat_with_content_proceeds(self) -> None:
        """When inject returns has_content=True, skip is NOT triggered."""
        builder = AsyncMock(spec=SituationReportBuilder)
        runner = AgentJobRunner(situation_builder=builder)
        job = _make_heartbeat_job()

        with (
            patch(
                _BUDGET_MODULE,
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch.object(
                runner,
                "_inject_situation_report",
                new_callable=AsyncMock,
                return_value=("enriched prompt", True),
            ),
        ):
            try:
                result = await runner._run_once(job)
            except Exception:
                result = None

        if result is not None:
            assert result.skipped is not True

    @pytest.mark.asyncio
    async def test_no_prompt_returns_error(self) -> None:
        runner = AgentJobRunner()
        job = _make_heartbeat_job(prompt="")
        result = await runner._run_once(job)
        assert not result.success
        assert "requires a prompt" in (result.error or "")

    @pytest.mark.asyncio
    async def test_budget_exceeded_blocks(self) -> None:
        runner = AgentJobRunner()
        job = _make_heartbeat_job()
        with patch(
            _BUDGET_MODULE,
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await runner._run_once(job)
        assert not result.success
        assert "budget" in (result.error or "").lower()


class TestRunRetry:
    """Tests for the retry logic in run()."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self) -> None:
        runner = AgentJobRunner()
        job = _make_heartbeat_job(max_retries=1, retry_backoff_ms=100)

        with patch.object(
            runner,
            "_run_once",
            new_callable=AsyncMock,
            side_effect=[
                JobResult(success=False, error="transient"),
                JobResult(success=True, output="ok"),
            ],
        ):
            result = await runner.run(job)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self) -> None:
        runner = AgentJobRunner()
        job = _make_heartbeat_job(max_retries=2, retry_backoff_ms=100)

        with patch.object(
            runner,
            "_run_once",
            new_callable=AsyncMock,
            return_value=JobResult(success=False, error="persistent"),
        ):
            result = await runner.run(job)

        assert not result.success
