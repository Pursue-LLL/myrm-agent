"""Tests for ShadowTester (Server layer)

Covers:
- Successful shadow test execution
- Failed shadow test (execution error)
- Comparator integration (uses real StructuredComparator)
- Result data integrity
"""

import pytest
from myrm_agent_harness.agent.skills.optimization.event_emitter import EventEmitter
from myrm_agent_harness.agent.skills.optimization.protocols import SkillExecutionProvider
from myrm_agent_harness.agent.skills.optimization.result_comparator import StructuredComparator

from app.services.skill_optimization.shadow_tester import ShadowTester, ShadowTestResult


class FakeExecutionProvider(SkillExecutionProvider):
    """Controllable fake for testing"""

    def __init__(self, result: dict[str, object] | None = None, error: Exception | None = None):
        self._result = result or {"status": "ok", "output": "shadow result"}
        self._error = error

    async def execute_skill_version(
        self,
        skill_id: str,
        version: int,
        inputs: dict[str, object],
        isolated_mode: bool = False,
    ) -> dict[str, object]:
        if self._error:
            raise self._error
        return self._result


@pytest.fixture
def emitter() -> EventEmitter:
    return EventEmitter()


@pytest.mark.asyncio
async def test_successful_shadow_test(emitter: EventEmitter) -> None:
    provider = FakeExecutionProvider(result={"status": "ok", "output": "candidate output"})
    tester = ShadowTester(execution_provider=provider, event_emitter=emitter)

    result = await tester.run_shadow_test(
        skill_id="test-skill",
        baseline_version=1,
        candidate_version=2,
        inputs={"query": "test"},
        baseline_result={"status": "ok", "output": "baseline output"},
        baseline_duration=0.5,
    )

    assert isinstance(result, ShadowTestResult)
    assert result.success is True
    assert result.error is None
    assert result.skill_id == "test-skill"
    assert result.baseline_version == 1
    assert result.candidate_version == 2
    assert result.candidate_duration >= 0
    assert result.comparison.similarity_score >= 0.0


@pytest.mark.asyncio
async def test_identical_results_match(emitter: EventEmitter) -> None:
    same_result: dict[str, object] = {"status": "ok", "output": "identical"}
    provider = FakeExecutionProvider(result=same_result)
    tester = ShadowTester(execution_provider=provider, event_emitter=emitter)

    result = await tester.run_shadow_test(
        skill_id="test-skill",
        baseline_version=1,
        candidate_version=2,
        inputs={"query": "test"},
        baseline_result=same_result,
        baseline_duration=0.5,
    )

    assert result.comparison.is_match is True
    assert result.comparison.similarity_score == 1.0


@pytest.mark.asyncio
async def test_failed_execution(emitter: EventEmitter) -> None:
    provider = FakeExecutionProvider(error=RuntimeError("Execution failed"))
    tester = ShadowTester(execution_provider=provider, event_emitter=emitter)

    result = await tester.run_shadow_test(
        skill_id="test-skill",
        baseline_version=1,
        candidate_version=2,
        inputs={"query": "test"},
        baseline_result={"status": "ok"},
        baseline_duration=0.5,
    )

    assert result.success is False
    assert result.error is not None
    assert "Execution failed" in result.error
    assert result.comparison.is_match is False
    assert result.comparison.similarity_score == 0.0


@pytest.mark.asyncio
async def test_custom_comparator(emitter: EventEmitter) -> None:
    provider = FakeExecutionProvider(result={"status": "ok", "output": "different"})
    strict_comparator = StructuredComparator(match_threshold=0.99)
    tester = ShadowTester(
        execution_provider=provider,
        event_emitter=emitter,
        comparator=strict_comparator,
    )

    result = await tester.run_shadow_test(
        skill_id="test-skill",
        baseline_version=1,
        candidate_version=2,
        inputs={"query": "test"},
        baseline_result={"status": "ok", "output": "slightly different"},
        baseline_duration=0.5,
    )

    assert result.comparison.is_match is False


@pytest.mark.asyncio
async def test_event_emitted_on_success(emitter: EventEmitter) -> None:
    events: list[tuple[str, dict]] = []

    async def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    emitter.on("shadow_test_completed", capture)

    provider = FakeExecutionProvider()
    tester = ShadowTester(execution_provider=provider, event_emitter=emitter)

    await tester.run_shadow_test(
        skill_id="test-skill",
        baseline_version=1,
        candidate_version=2,
        inputs={},
        baseline_result={"status": "ok"},
        baseline_duration=0.5,
    )

    assert len(events) == 1
    assert events[0][0] == "shadow_test_completed"
    assert events[0][1]["skill_id"] == "test-skill"


@pytest.mark.asyncio
async def test_event_emitted_on_failure(emitter: EventEmitter) -> None:
    events: list[tuple[str, dict]] = []

    async def capture(event: str, payload: dict) -> None:
        events.append((event, payload))

    emitter.on("shadow_test_failed", capture)

    provider = FakeExecutionProvider(error=RuntimeError("boom"))
    tester = ShadowTester(execution_provider=provider, event_emitter=emitter)

    await tester.run_shadow_test(
        skill_id="test-skill",
        baseline_version=1,
        candidate_version=2,
        inputs={},
        baseline_result={},
        baseline_duration=0.0,
    )

    assert len(events) == 1
    assert events[0][0] == "shadow_test_failed"
    assert "boom" in events[0][1]["error"]
