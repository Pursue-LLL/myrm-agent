"""A scheduled run that stops on a question for a person is recorded as failed and never repeated, not as done."""

from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.agent.streaming.interrupt_events import interrupt_events
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.agent_runner.stream import (
    _consume_dynamic_workflow_stream,
    _consume_stream,
    _StreamAccumulator,
)

_PAUSED_ERROR = (
    "The run stopped at a step that needs a person's answer. A scheduled run has nobody to ask, so the rest of it did not run."
)

# Graph interrupt values by the event type the agent stream turns each into.
_INTERRUPTS: dict[str, dict[str, object]] = {
    "tool_approval_request": {"actionRequests": [{"name": "git_push_tool", "args": {}}]},
    "approval_required": {"action_type": "browser_takeover"},
    "clarification_required": {"type": "ask_question", "questions": []},
    "swarm_fission": {"action_type": "swarm_fission", "tasks": []},
}


def _job() -> CronJob:
    return CronJob(
        id="cron-1",
        name="Daily report",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        status=JobStatus.ACTIVE,
        prompt="Generate the report.",
        delivery=DeliveryConfig(channel="chat"),
        max_retries=2,
    )


def _pause_event(interrupt_value: dict[str, object]) -> dict[str, object]:
    """The event the agent stream emits when the graph pauses on ``interrupt_value`` (the producer's own conversion)."""
    (event,) = interrupt_events([SimpleNamespace(value=interrupt_value, id="int-1")], "m1")
    return event


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


_PARTIAL: dict[str, object] = {"type": "message", "data": "partial report"}
_ERROR: dict[str, object] = {"type": "error", "error": "provider overloaded", "error_type": "LLMError"}
_WORKFLOW_STEP: dict[str, object] = {"type": "status", "data": {"step_key": "collect"}}
_PAUSE_KINDS = list(_INTERRUPTS)


def test_the_real_stream_names_each_pause() -> None:
    """The consumers match on these event types, so the producer and the consumers must agree on them."""
    assert {kind: _pause_event(value)["type"] for kind, value in _INTERRUPTS.items()} == {kind: kind for kind in _INTERRUPTS}


class TestAgentRun:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", _PAUSE_KINDS)
    async def test_a_pause_ends_the_run_as_a_failure_that_is_not_repeated(self, kind: str) -> None:
        agent = _agent_streaming([_PARTIAL, _pause_event(_INTERRUPTS[kind])])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is False
        assert result.retry_safe is False
        assert result.error == _PAUSED_ERROR
        assert result.output == "partial report"

    @pytest.mark.asyncio
    async def test_a_loop_guard_pause_ends_the_run_too(self) -> None:
        """The pause is an interrupt like any other: nothing continues the run, so it did not finish."""
        stuck = ToolStuckException("TOOL_STUCK_EXCEPTION: the tool failed 3 times in a row")
        agent = _agent_streaming([_pause_event(stuck.interrupt_payload("web_fetch_tool", "call-1"))])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is False
        assert result.retry_safe is False

    @pytest.mark.asyncio
    async def test_the_accumulator_remembers_the_pause(self) -> None:
        acc = _StreamAccumulator()
        agent = _agent_streaming([_pause_event(_INTERRUPTS["tool_approval_request"])])

        await _consume_stream(agent, _job(), "prompt", {}, acc, untrusted=False)

        assert acc.paused is True

    @pytest.mark.asyncio
    async def test_a_run_that_failed_keeps_its_own_error(self) -> None:
        agent = _agent_streaming([_pause_event(_INTERRUPTS["approval_required"]), _ERROR])

        result = await _consume_stream(agent, _job(), "prompt", {}, _StreamAccumulator(), untrusted=False)

        assert result.success is False
        assert result.error == "LLMError: provider overloaded"

    @pytest.mark.asyncio
    async def test_a_run_that_reached_its_end_is_still_a_success(self) -> None:
        agent = _agent_streaming([_PARTIAL, {"type": "message_end", "usage": {"total_tokens": 7}}])
        acc = _StreamAccumulator()

        result = await _consume_stream(agent, _job(), "prompt", {}, acc, untrusted=False)

        assert result.success is True
        assert result.retry_safe is True
        assert acc.paused is False


class TestWorkflowRun:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("kind", _PAUSE_KINDS)
    async def test_a_pause_ends_the_run_as_a_failure_that_is_not_repeated(self, kind: str) -> None:
        stream = _workflow_events([_WORKFLOW_STEP, _pause_event(_INTERRUPTS[kind])])

        result = await _consume_dynamic_workflow_stream(stream, _job(), None, _StreamAccumulator())

        assert result.success is False
        assert result.retry_safe is False
        assert result.error == _PAUSED_ERROR

    @pytest.mark.asyncio
    async def test_a_run_that_failed_keeps_its_own_error(self) -> None:
        stream = _workflow_events([_WORKFLOW_STEP, _pause_event(_INTERRUPTS["approval_required"]), _ERROR])

        result = await _consume_dynamic_workflow_stream(stream, _job(), None, _StreamAccumulator())

        assert result.error == "LLMError: provider overloaded"

    @pytest.mark.asyncio
    async def test_a_run_that_reached_its_end_is_still_a_success(self) -> None:
        stream = _workflow_events([_WORKFLOW_STEP, _PARTIAL, {"type": "message_end", "usage": {"total_tokens": 7}}])

        result = await _consume_dynamic_workflow_stream(stream, _job(), None, _StreamAccumulator())

        assert result.success is True
