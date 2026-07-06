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
