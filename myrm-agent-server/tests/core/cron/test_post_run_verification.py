"""Unit tests for cron post-run delivery verification helpers."""

from myrm_agent_harness.toolkits.cron.types import JobResult

from app.core.cron.adapters.post_run_verification import (
    _has_effectful_tools,
    apply_cron_post_run_verification,
)


def test_has_effectful_tools_detects_write_tools() -> None:
    steps = [{"tool_name": "web_search_tool"}, {"tool_name": "file_write_tool"}]
    assert _has_effectful_tools(steps) is True


def test_has_effectful_tools_ignores_read_only_tools() -> None:
    steps = [{"tool_name": "file_read_tool"}, {"tool_name": "grep_tool"}]
    assert _has_effectful_tools(steps) is False


async def test_apply_skips_when_disabled() -> None:
    base = JobResult(success=True, output="done", metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]})
    result = await apply_cron_post_run_verification(object(), object(), base, enabled=False)
    assert result.metadata is None or "verification" not in (result.metadata or {})


async def test_apply_skips_without_effectful_tools() -> None:
    base = JobResult(success=True, output="done", metadata={"progressSteps": [{"tool_name": "grep_tool"}]})
    result = await apply_cron_post_run_verification(object(), object(), base, enabled=True)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "skipped"


async def test_apply_fail_keeps_cron_success(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents._verification_parsing import VerificationVerdict
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig
    from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind

    async def _fake_verify(*_args, **_kwargs):
        return VerificationVerdict(
            passed=False,
            summary="Side effect mismatch",
            confidence="HIGH",
            findings=[],
            raw="",
        )

    monkeypatch.setattr(
        "app.core.cron.adapters.post_run_verification.verify_worker_output",
        _fake_verify,
    )

    class _FakeCatalog:
        async def resolve(self, _name: str) -> SubagentConfig:
            return SubagentConfig(system_prompt="verifier")

    monkeypatch.setattr(
        "app.ai_agents.subagent_catalog.DatabaseSubagentCatalog",
        _FakeCatalog,
    )

    class _FakeSkillAgent:
        _subagent_manager = object()
        _cached_tools: list[object] = []
        user_tools: list[object] = []
        _last_context: dict[str, object] = {}

    class _FakeGeneralAgent:
        agent = _FakeSkillAgent()

    monkeypatch.setattr(
        "app.core.cron.adapters.post_run_verification.GeneralAgent",
        _FakeGeneralAgent,
    )

    job = CronJob(
        id="job-1",
        user_id="user-1",
        name="test",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expression="0 * * * *"),
        agent_id="agent-1",
    )
    base = JobResult(
        success=True,
        output="task done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(_FakeGeneralAgent(), job, base, enabled=True)
    assert result.success is True
    assert (result.metadata or {}).get("verification", {}).get("status") == "fail"
    assert "[Delivery verification: FAIL]" in (result.output or "")
