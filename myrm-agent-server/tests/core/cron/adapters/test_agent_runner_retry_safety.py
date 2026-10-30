"""A cron run whose steps may already have taken effect is not repeated in-process, and no result rebuild forgets that."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage
from myrm_agent_harness.agent.streaming.event_handlers import process_updates_chunk
from myrm_agent_harness.agent.types import AgentRunStatistics
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


def _effectful_run() -> _StreamAccumulator:
    return _StreamAccumulator(progress_steps=[{"tool_name": "send_message"}])


async def _tool_call_events(*tool_names: str) -> list[dict[str, object]]:
    """The events the real agent stream emits when the model calls ``tool_names`` (not hand-written look-alikes)."""
    message = AIMessage(
        content="",
        tool_calls=[{"name": name, "args": {}, "id": f"call-{i}"} for i, name in enumerate(tool_names)],
    )
    return [event async for event in process_updates_chunk({"model": {"messages": [message]}}, AgentRunStatistics(), "m1")]


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
    async def test_the_real_stream_names_every_called_tool(self) -> None:
        """The retry decision reads tool names from these events, so producer and consumer must agree on the field."""
        events = await _tool_call_events("web_search_tool", "send_message")

        assert [(event["type"], event["tool_name"]) for event in events] == [
            ("tasks_steps", "web_search_tool"),
            ("tasks_steps", "send_message"),
        ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tools",
        [["web_search_tool"], ["web_search_tool", "web_fetch_tool", "file_read_tool"]],
    )
    async def test_failure_after_read_only_tools_stays_retry_safe(self, tools: list[str]) -> None:
        acc = _StreamAccumulator()
        agent = _agent_streaming([*await _tool_call_events(*tools), _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, acc, untrusted=False)

        assert result.success is False
        assert result.retry_safe is True
        assert acc.effectful is False

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tools",
        [
            ["send_message"],
            ["execute_command"],
            ["delegate_task_tool"],
            ["web_search_tool", "send_message"],
            ["unregistered_tool"],
        ],
    )
    async def test_failure_after_a_state_changing_or_unknown_tool_is_not_retry_safe(self, tools: list[str]) -> None:
        acc = _StreamAccumulator()
        agent = _agent_streaming([*await _tool_call_events(*tools), _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, acc, untrusted=False)

        assert result.success is False
        assert result.retry_safe is False
        assert acc.effectful is True

    @pytest.mark.asyncio
    async def test_a_tool_call_the_model_was_still_writing_has_not_run(self) -> None:
        """``tool_start`` fires while the call is being generated; a stream that dies there executed nothing."""
        agent = _agent_streaming([_TOOL_START, _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is False
        assert result.retry_safe is True

    @pytest.mark.asyncio
    async def test_progress_markers_without_a_tool_name_are_not_tool_calls(self) -> None:
        marker: dict[str, object] = {"type": "tasks_steps", "step_key": "reviewing_sources", "tool_name": None, "count": 2}
        agent = _agent_streaming([marker, _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.retry_safe is True

    @pytest.mark.asyncio
    async def test_a_failed_read_only_tool_call_does_not_make_the_run_unsafe(self) -> None:
        failed_step: dict[str, object] = {
            "type": "tasks_steps",
            "step_key": "web_fetch_error",
            "tool_name": "web_fetch_tool",
            "status": "error",
            "error": "404",
        }
        agent = _agent_streaming([*await _tool_call_events("web_fetch_tool"), failed_step, _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.retry_safe is True

    @pytest.mark.asyncio
    async def test_failure_before_any_tool_call_stays_retry_safe(self) -> None:
        agent = _agent_streaming([{"type": "message", "data": "partial"}, _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is False
        assert result.retry_safe is True

    @pytest.mark.asyncio
    async def test_a_successful_run_that_changed_state_is_marked_too(self) -> None:
        """Acceptance verification can still fail this result later; it must not look repeatable then."""
        agent = _agent_streaming([*await _tool_call_events("send_message"), {"type": "message", "data": "done"}])

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
    def test_timeout_is_never_retry_safe(self) -> None:
        """A repeat would spend the same time budget again, whatever tools the run had used."""
        result = _timeout_result(_job(timeout_seconds=30))

        assert result.retry_safe is False
        assert result.error == "agent timed out after 30s"

    def test_crash_after_a_state_changing_tool_is_not_retry_safe(self) -> None:
        assert _failure_result(_job(), RuntimeError("boom"), _effectful_run()).retry_safe is False

    def test_crash_after_read_only_tools_is_retry_safe(self) -> None:
        acc = _StreamAccumulator(progress_steps=[{"tool_name": "web_search_tool"}])

        assert _failure_result(_job(), RuntimeError("boom"), acc).retry_safe is True

    def test_crash_before_any_tool_is_retry_safe(self) -> None:
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
    async def test_failure_that_is_not_safe_to_repeat_runs_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        failed = JobResult(success=False, error="boom", retry_safe=False)
        runner, run_once = self._runner(monkeypatch, [failed])

        result = await runner._run_with_retries(_job(max_retries=2), context="")

        assert result is failed
        assert run_once.await_count == 1

    @pytest.mark.asyncio
    async def test_a_timeout_runs_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner, run_once = self._runner(monkeypatch, [_timeout_result(_job())])

        result = await runner._run_with_retries(_job(max_retries=2), context="")

        assert result.retry_safe is False
        assert run_once.await_count == 1

    @pytest.mark.asyncio
    async def test_failure_that_is_safe_to_repeat_uses_every_attempt(self, monkeypatch: pytest.MonkeyPatch) -> None:
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
