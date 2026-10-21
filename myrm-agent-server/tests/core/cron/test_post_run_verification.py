"""Unit tests for cron post-run delivery verification helpers."""

import time
from types import SimpleNamespace

import pytest
from myrm_agent_harness.agent.sub_agents.types import SubAgentResult, SubAgentStatus
from myrm_agent_harness.toolkits.cron.types import CronJob, JobResult, JobType, Schedule, ScheduleKind

from app.core.cron.adapters.post_run_verification import (
    _has_effectful_tools,
    apply_cron_post_run_verification,
)


def _minimal_cron_job(**overrides: object) -> CronJob:
    payload: dict[str, object] = {
        "id": "job-1",
        "user_id": "user-1",
        "name": "test",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
    }
    payload.update(overrides)
    return CronJob(**payload)  # type: ignore[arg-type]


def _patch_general_agent(monkeypatch, skill_agent: object | None) -> type:
    class _FakeGeneralAgent:
        agent = skill_agent

    monkeypatch.setattr(
        "app.ai_agents.general_agent.GeneralAgent",
        _FakeGeneralAgent,
    )
    return _FakeGeneralAgent


def test_has_effectful_tools_detects_write_tools() -> None:
    steps = [{"tool_name": "web_search_tool"}, {"tool_name": "file_write_tool"}]
    assert _has_effectful_tools(steps) is True


def test_has_effectful_tools_detects_browser_tools() -> None:
    steps = [{"tool_name": "browser_navigate_tool"}]
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


async def test_apply_skips_when_no_time_budget() -> None:
    base = JobResult(success=True, output="done", metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]})
    result = await apply_cron_post_run_verification(object(), object(), base, enabled=True, timeout_seconds=0)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "skipped"


async def test_apply_fail_keeps_cron_success(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents._verification_parsing import VerificationVerdict
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

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

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())

    job = _minimal_cron_job(agent_id="agent-1")
    base = JobResult(
        success=True,
        output="task done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), job, base, enabled=True)
    assert result.success is True
    assert (result.metadata or {}).get("verification", {}).get("status") == "fail"
    assert "[Delivery verification: FAIL]" in (result.output or "")


def _verifier_result(kwargs: dict[str, object], *, success: bool) -> SubAgentResult:
    return SubAgentResult(
        success=success,
        task_id=str(kwargs["task_id"]),
        agent_type=str(kwargs["agent_type"]),
        result="done" if success else "",
        error="" if success else "verifier crashed",
        completed_at=time.time(),
        status=SubAgentStatus.COMPLETED if success else SubAgentStatus.FAILED,
    )


async def _crashed_verifier(**kwargs: object) -> SubAgentResult:
    return _verifier_result(kwargs, success=False)


async def _lazy_passing_verifier(**kwargs: object) -> SubAgentResult:
    """Submits PASS through the real tool without ever launching a command."""
    tool_registry_getter = kwargs["tool_registry_getter"]
    assert callable(tool_registry_getter)
    submit = next(tool for tool in tool_registry_getter() if tool.name == "submit_verdict")
    submit.invoke({"passed": True, "summary": "Looks fine", "findings": [], "confidence": "HIGH"})
    return _verifier_result(kwargs, success=True)


@pytest.mark.parametrize("spawn_child", [_crashed_verifier, _lazy_passing_verifier])
async def test_apply_inconclusive_verifier_is_reported_as_error_without_a_fail_note(monkeypatch, spawn_child) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    class _FakeCatalog:
        async def resolve(self, _name: str) -> SubagentConfig:
            return SubagentConfig(system_prompt="verifier")

    monkeypatch.setattr("app.ai_agents.subagent_catalog.DatabaseSubagentCatalog", _FakeCatalog)

    class _FakeSkillAgent:
        _subagent_manager = SimpleNamespace(spawn_child=spawn_child)
        _cached_tools: list[object] = []
        user_tools: list[object] = []
        _last_context: dict[str, object] = {}

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())

    base = JobResult(
        success=True,
        output="task done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), _minimal_cron_job(), base, enabled=True)

    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "error"
    assert verification.get("summary") == "Verifier did not reach a conclusive verdict"
    assert result.success is True
    assert result.output == "task done"


async def test_apply_returns_unchanged_when_agent_is_not_general_agent() -> None:
    base = JobResult(
        success=True,
        output="done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(object(), object(), base, enabled=True)
    assert result is base
    assert result.metadata is None or "verification" not in (result.metadata or {})


async def test_apply_error_when_skill_agent_missing(monkeypatch) -> None:
    fake_cls = _patch_general_agent(monkeypatch, None)
    base = JobResult(
        success=True,
        output="done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), _minimal_cron_job(), base, enabled=True)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "error"


async def test_apply_error_when_subagent_manager_missing(monkeypatch) -> None:
    class _FakeSkillAgent:
        _cached_tools: list[object] = []
        user_tools: list[object] = []
        _last_context: dict[str, object] = {}

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())
    base = JobResult(
        success=True,
        output="done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), _minimal_cron_job(), base, enabled=True)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "error"


async def test_apply_skips_on_empty_output(monkeypatch) -> None:
    class _FakeSkillAgent:
        _subagent_manager = object()
        _cached_tools: list[object] = []
        user_tools: list[object] = []
        _last_context: dict[str, object] = {}

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())
    base = JobResult(
        success=True,
        output="   ",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), _minimal_cron_job(), base, enabled=True)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "skipped"


async def test_apply_error_when_verifier_preset_missing(monkeypatch) -> None:
    class _FakeCatalog:
        async def resolve(self, _name: str) -> None:
            return None

    monkeypatch.setattr(
        "app.ai_agents.subagent_catalog.DatabaseSubagentCatalog",
        _FakeCatalog,
    )

    class _FakeSkillAgent:
        _subagent_manager = object()
        _cached_tools: list[object] = []
        user_tools: list[object] = []
        _last_context: dict[str, object] = {}

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())
    base = JobResult(
        success=True,
        output="done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), _minimal_cron_job(), base, enabled=True)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "error"


async def test_apply_pass_does_not_append_fail_note(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents._verification_parsing import VerificationVerdict
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    async def _fake_verify(*_args, **_kwargs):
        return VerificationVerdict(
            passed=True,
            summary="Looks good",
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

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())

    job = _minimal_cron_job(id="job-pass")
    base = JobResult(
        success=True,
        output="task done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), job, base, enabled=True)
    assert result.success is True
    assert result.output == "task done"
    assert (result.metadata or {}).get("verification", {}).get("status") == "pass"
    assert (result.metadata or {}).get("deliverable_tier", {}).get("tier") == "VERIFIED"


async def test_apply_timeout_records_error(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    async def _slow_verify(*_args, **_kwargs):
        raise TimeoutError

    monkeypatch.setattr(
        "app.core.cron.adapters.post_run_verification.verify_worker_output",
        _slow_verify,
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

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())

    base = JobResult(
        success=True,
        output="done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(
        fake_cls(),
        _minimal_cron_job(),
        base,
        enabled=True,
        timeout_seconds=120,
    )
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "error"


async def test_apply_exception_records_error(monkeypatch) -> None:
    from myrm_agent_harness.agent.sub_agents.types import SubagentConfig

    async def _broken_verify(*_args, **_kwargs):
        raise RuntimeError("spawn failed")

    monkeypatch.setattr(
        "app.core.cron.adapters.post_run_verification.verify_worker_output",
        _broken_verify,
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

    fake_cls = _patch_general_agent(monkeypatch, _FakeSkillAgent())

    base = JobResult(
        success=True,
        output="done",
        metadata={"progressSteps": [{"tool_name": "bash_code_execute_tool"}]},
    )
    result = await apply_cron_post_run_verification(fake_cls(), _minimal_cron_job(), base, enabled=True)
    verification = (result.metadata or {}).get("verification")
    assert isinstance(verification, dict)
    assert verification.get("status") == "error"
    assert "spawn failed" in str(verification.get("summary"))
