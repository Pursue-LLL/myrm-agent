"""run_verify_command: where the command runs, and a command that judged the file versus one that never ran."""

from __future__ import annotations

from unittest.mock import AsyncMock, PropertyMock

from myrm_agent_harness.agent.meta_tools.file_ops.core.verify_runner import run_verify_command
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext, ExecutionResult

_BLOCKED = "Command blocked for security reasons: Python inline execution (python -c )"


def _executor(result: ExecutionResult | None = None, *, workspace: str = "/ws") -> AsyncMock:
    executor = AsyncMock()
    executor.workspace_path = workspace
    executor.execute_bash.return_value = result
    return executor


def _context_of(executor: AsyncMock) -> ExecutionContext:
    context = executor.execute_bash.await_args.args[0]
    assert isinstance(context, ExecutionContext)
    return context


async def test_an_exit_code_of_zero_passes() -> None:
    executor = _executor(ExecutionResult(success=True, exit_code=0, stdout="ok"))

    outcome = await run_verify_command(executor, "pytest -q", "a.py")

    assert outcome.verdict == "passed"
    assert not outcome.failed
    assert not outcome.not_run


async def test_a_non_zero_exit_code_fails_and_the_report_carries_what_the_model_needs_to_fix_it() -> None:
    executor = _executor(ExecutionResult(success=False, exit_code=2, stdout="1 failed", stderr="boom"))

    outcome = await run_verify_command(executor, "pytest -q", "a.py")

    assert outcome.failed
    assert outcome.exit_code == 2
    report = outcome.failure_report()
    for expected in ("Command: pytest -q", "Exit code: 2", "Stdout: 1 failed", "Stderr: boom", "Please fix"):
        assert expected in report


async def test_an_exit_the_executor_calls_informational_passes_as_it_does_in_the_bash_tool() -> None:
    """``grep`` finding nothing exits 1 and the executor reports it as a success; the verdict follows it."""
    executor = _executor(ExecutionResult(success=True, exit_code=1))

    outcome = await run_verify_command(executor, "grep -q TODO a.py", "a.py")

    assert outcome.verdict == "passed"


async def test_a_timeout_is_a_verdict_not_a_missing_run() -> None:
    executor = _executor(ExecutionResult(success=False, exit_code=124, error="Timeout", stderr="Timeout after 60s"))

    outcome = await run_verify_command(executor, "pytest", "a.py")

    assert outcome.failed


async def test_a_command_the_safety_check_blocks_never_ran() -> None:
    executor = _executor(ExecutionResult(success=False, error=_BLOCKED, stderr=_BLOCKED))

    outcome = await run_verify_command(executor, "python -c 'print(1)'", "a.py")

    assert outcome.not_run
    assert not outcome.failed
    assert "python -c" in outcome.reason
    assert "kept unchecked" in outcome.not_run_note()
    assert outcome.reason in outcome.not_run_note()


async def test_an_executor_that_raises_means_the_command_never_ran() -> None:
    executor = _executor()
    executor.execute_bash.side_effect = PermissionError("Bash execution is blocked in shadow context.")

    outcome = await run_verify_command(executor, "pytest", "a.py")

    assert outcome.not_run
    assert outcome.reason == "PermissionError: Bash execution is blocked in shadow context."


async def test_the_reason_is_one_line_masked_and_cut() -> None:
    secret = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
    error = f"first line\napi_key: {secret}\n" + "x" * 1000
    executor = _executor(ExecutionResult(success=False, error=error))

    outcome = await run_verify_command(executor, "pytest", "a.py")

    assert "\n" not in outcome.reason
    assert "abcdefghijklmnopqrstuvwxyz" not in outcome.reason
    assert len(outcome.reason) <= 300


async def test_the_command_runs_from_the_workspace_root_whatever_directory_the_shell_is_in() -> None:
    executor = _executor(ExecutionResult(success=True, exit_code=0), workspace="/srv/ws")

    await run_verify_command(executor, "python -m py_compile pkg/mod.py", "pkg/mod.py")

    context = _context_of(executor)
    assert context.code == "python -m py_compile pkg/mod.py"
    assert context.work_dir == "/workspace"
    assert context.enter_work_dir is True
    assert context.workspace_root == "/srv/ws"


async def test_an_executor_bound_to_no_workspace_still_runs_the_command() -> None:
    executor = _executor(ExecutionResult(success=True, exit_code=0))
    type(executor).workspace_path = PropertyMock(side_effect=RuntimeError("Workspace not bound"))

    outcome = await run_verify_command(executor, "pytest", "a.py")

    assert outcome.verdict == "passed"
    assert _context_of(executor).workspace_root is None
