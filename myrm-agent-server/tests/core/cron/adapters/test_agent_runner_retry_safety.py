"""A cron run that already called tools is not repeated in-process, and no result rebuild forgets that."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters import agent_runner
from app.core.cron.adapters.acceptance_verification import _with_verification_metadata
from app.core.cron.adapters.agent_runner import (
    AgentJobRunner,
    _consume_dynamic_workflow_stream,
    _consume_stream,
    _failure_result,
    _StreamAccumulator,
    _timeout_result,
)
from app.core.cron.adapters.post_run_verification import _attach_verification_metadata


def _job(**overrides: object) -> CronJob:
    fields: dict[str, object] = {
        "id": "cron-1",
        "user_id": "user-1",
        "name": "Daily report",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Generate the report.",
        "delivery": DeliveryConfig(channel="chat"),
        "max_retries": 2,
    }
    fields.update(overrides)
    return CronJob(**fields)  # type: ignore[arg-type]


def _used_tools() -> _StreamAccumulator:
    return _StreamAccumulator(tool_used=True)


def _agent_streaming(events: list[dict[str, object]]) -> MagicMock:
    """A GeneralAgent stand-in whose stream replays ``events``."""
    from app.ai_agents.general_agent import GeneralAgent

    async def _process_stream(**_kwargs: object) -> AsyncIterator[dict[str, object]]:
        for event in events:
            yield event

    agent = MagicMock(spec=GeneralAgent)
    agent.model_cfg = SimpleNamespace(model="test-model")
    agent.process_stream = _process_stream
    return agent


async def _workflow_events(events: list[dict[str, object]]) -> AsyncIterator[dict[str, object]]:
    for event in events:
        yield event


_TOOL_START: dict[str, object] = {"type": "tool_start", "messageId": "m1"}
_ERROR: dict[str, object] = {"type": "error", "error": "provider overloaded", "error_type": "LLMError"}


class TestStreamConsumers:
    @pytest.mark.asyncio
    async def test_failure_after_a_tool_call_is_not_retry_safe(self) -> None:
        acc = _StreamAccumulator()
        agent = _agent_streaming([_TOOL_START, _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, acc, untrusted=False)

        assert result.success is False
        assert result.retry_safe is False
        assert acc.tool_used is True

    @pytest.mark.asyncio
    async def test_failure_before_any_tool_call_stays_retry_safe(self) -> None:
        agent = _agent_streaming([{"type": "message", "data": "partial"}, _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is False
        assert result.retry_safe is True

    @pytest.mark.asyncio
    async def test_a_successful_run_that_used_tools_is_marked_too(self) -> None:
        """Acceptance verification can still fail this result later; it must not look repeatable then."""
        agent = _agent_streaming([_TOOL_START, {"type": "message", "data": "done"}])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is True
        assert result.retry_safe is False

    @pytest.mark.asyncio
    async def test_workflow_step_counts_as_work_done(self) -> None:
        stream = _workflow_events([{"type": "status", "data": {"step_key": "collect"}}, _ERROR])

        result = await _consume_dynamic_workflow_stream(stream, _job(), None, _StreamAccumulator())

        assert result.success is False
        assert result.retry_safe is False

    @pytest.mark.asyncio
    async def test_workflow_failing_before_any_step_stays_retry_safe(self) -> None:
        result = await _consume_dynamic_workflow_stream(_workflow_events([_ERROR]), _job(), None, _StreamAccumulator())

        assert result.success is False
        assert result.retry_safe is True


class TestRunOutcomeBuilders:
    def test_timeout_after_tool_use_is_not_retry_safe(self) -> None:
        assert _timeout_result(_job(timeout_seconds=30), _used_tools()).retry_safe is False

    def test_timeout_before_tool_use_is_retry_safe(self) -> None:
        result = _timeout_result(_job(timeout_seconds=30), _StreamAccumulator())

        assert result.retry_safe is True
        assert result.error == "agent timed out after 30s"

    def test_crash_after_tool_use_is_not_retry_safe(self) -> None:
        assert _failure_result(_job(), RuntimeError("boom"), _used_tools()).retry_safe is False

    def test_crash_before_tool_use_is_retry_safe(self) -> None:
        assert _failure_result(_job(), RuntimeError("boom"), _StreamAccumulator()).retry_safe is True


class TestResultRebuilds:
    """Verification steps rebuild the run's result; they must carry every field over, ``retry_safe`` included."""

    def test_failed_acceptance_criteria_keep_the_run_unrepeatable(self) -> None:
        ran = JobResult(success=True, output="report", exit_code=0, retry_safe=False)

        rebuilt = _with_verification_metadata(ran, status="fail", passed=False, summary="missing totals", success_override=False)

        assert rebuilt.success is False
        assert rebuilt.exit_code == 2
        assert rebuilt.output == "report"
        assert rebuilt.retry_safe is False

    def test_post_run_verification_metadata_keeps_every_other_field(self) -> None:
        retry_at = datetime(2026, 3, 1, tzinfo=timezone.utc)
        ran = JobResult(
            success=True,
            output="report",
            exit_code=7,
            circuit_broken=True,
            retry_at=retry_at,
            skip_reason="why",
            retry_safe=False,
        )

        rebuilt = _attach_verification_metadata(ran, status="skipped", passed=None, summary="nothing to verify")

        assert rebuilt.metadata is not None
        assert rebuilt.metadata["verification"]["status"] == "skipped"
        assert (rebuilt.exit_code, rebuilt.circuit_broken, rebuilt.retry_at, rebuilt.skip_reason, rebuilt.retry_safe) == (
            7,
            True,
            retry_at,
            "why",
            False,
        )


class TestInProcessRetries:
    @staticmethod
    def _runner(monkeypatch: pytest.MonkeyPatch, outcomes: list[JobResult]) -> tuple[AgentJobRunner, AsyncMock]:
        monkeypatch.setattr(agent_runner, "_memory_overload_reason", lambda: None)
        monkeypatch.setattr(agent_runner.asyncio, "sleep", AsyncMock())
        runner = AgentJobRunner()
        run_once = AsyncMock(side_effect=outcomes)
        monkeypatch.setattr(runner, "_run_once", run_once)
        return runner, run_once

    @pytest.mark.asyncio
    async def test_failure_after_tool_use_runs_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        failed = JobResult(success=False, error="boom", retry_safe=False)
        runner, run_once = self._runner(monkeypatch, [failed])

        result = await runner._run_with_retries(_job(max_retries=2), context="")

        assert result is failed
        assert run_once.await_count == 1

    @pytest.mark.asyncio
    async def test_failure_before_tool_use_uses_every_attempt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner, run_once = self._runner(monkeypatch, [JobResult(success=False, error="boom")] * 3)

        result = await runner._run_with_retries(_job(max_retries=2), context="")

        assert result.success is False
        assert run_once.await_count == 3

    @pytest.mark.asyncio
    async def test_a_retry_that_succeeds_ends_the_loop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ok = JobResult(success=True, output="done")
        runner, run_once = self._runner(monkeypatch, [JobResult(success=False, error="boom"), ok])

        result = await runner._run_with_retries(_job(max_retries=2), context="")

        assert result is ok
        assert run_once.await_count == 2
