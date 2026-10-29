"""A verification command that exits non-zero has failed, whatever its output says.

The outputs below are what ruff, tsc and pytest print for a failing run. Their text
carries none of the failure keywords the success evaluator looks for, so only the
``[exit_code: N]`` line the bash tool appends says the run failed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.agent.meta_tools.bash._tool.formatting import format_result
from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist.record_rules import (
    failed_verification_types,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.verification import (
    tag_verification_call,
)
from myrm_agent_harness.agent.middlewares.tooling._tool_guards import run_post_call_guards
from myrm_agent_harness.agent.security.guards.context_budget import BudgetAction
from myrm_agent_harness.agent.security.guards.frequency_guard import FrequencyAction
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    LoopAction,
    LoopGuard,
    SuccessLevel,
    VerificationCategory,
)
from myrm_agent_harness.agent.security.guards.loop_guard.suggestions import evaluate_success_level

_BASH = "bash_code_execute_tool"

_RUFF_FAILING = """F401 [*] `os` imported but unused
 --> bad.py:1:8
  |
1 | import os
  |        ^^
2 | x = 1
  |
help: Remove unused import: `os`

Found 1 error.
[*] 1 fixable with the `--fix` option.
"""
_TSC_FAILING = "a.ts(1,7): error TS2322: Type 'number' is not assignable to type 'string'.\n"
_PYTEST_SUMMARY_FAILING = (
    "F                                                                        [100%]\n"
    "=========================== short test summary info ============================\n"
    "FAILED test_a.py::test_a - assert 1 == 2\n"
    "1 failed in 0.00s\n"
)
_PYTEST_FULL_FAILING = """============================= test session starts ==============================
collected 1 item

test_a.py F                                                              [100%]

=================================== FAILURES ===================================
___________________________________ test_a ____________________________________

    def test_a():
>       assert 1 == 2
E       assert 1 == 2

test_a.py:2: AssertionError
=========================== short test summary info ============================
FAILED test_a.py::test_a - assert 1 == 2
============================== 1 failed in 0.01s ===============================
"""
_PYTEST_NOTHING_COLLECTED = (
    "============================= test session starts ==============================\n"
    "collected 0 items\n\n"
    "============================ no tests ran in 0.00s =============================\n"
)
_RUFF_PASSING = "All checks passed!\n"


def _formatted(command: str, stdout: str, exit_code: int | str, stderr: str = "") -> str:
    text, _, _ = format_result({"stdout": stdout, "stderr": stderr, "exit_code": exit_code}, command)
    return text


def _envelope(text: str) -> str:
    """The shape the bash tool result has by the time the post-call guard reads it."""
    return json.dumps({"content": text, "metadata": {}})


def _tagged(command: str, result_text: str, judged: SuccessLevel | None = None) -> tuple[CallRecord, SuccessLevel]:
    """Tag a finished bash call as the post-call guard does; return it with its level beforehand.

    The output judge's own verdict is used unless the test pins one.
    """
    record = CallRecord(tool_name=_BASH, args_hash="h", args={"command": command})
    record.success_level = judged or evaluate_success_level(_BASH, result_text)
    before = record.success_level
    tag_verification_call(record, {"command": command}, result_text)
    return record, before


@pytest.mark.parametrize("wrap", [lambda text: text, _envelope], ids=["plain", "json-envelope"])
@pytest.mark.parametrize(
    ("command", "stdout", "stderr", "exit_code", "category"),
    [
        ("ruff check bad.py", _RUFF_FAILING, "", 1, VerificationCategory.LINT),
        ("npx tsc --noEmit --strict a.ts", _TSC_FAILING, "", 2, VerificationCategory.TYPECHECK),
        ("pytest -q --tb=no test_a.py", _PYTEST_SUMMARY_FAILING, "", 1, VerificationCategory.TEST),
        ("ruff check .", "", "sh: ruff: command not found", 127, VerificationCategory.LINT),
    ],
    ids=["ruff-1", "tsc-2", "pytest-summary-only-1", "command-not-found-127"],
)
def test_non_zero_exit_fails_a_verification_run(
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
    category: VerificationCategory,
    wrap: Callable[[str], str],
) -> None:
    record, _ = _tagged(command, wrap(_formatted(command, stdout, exit_code, stderr)))

    assert record.verification_type == category
    assert record.success_level == SuccessLevel.FAILURE


@pytest.mark.parametrize(
    ("command", "stdout", "exit_code", "judged"),
    [
        ("ruff check .", _RUFF_PASSING, 0, SuccessLevel.FULL_SUCCESS),
        ("ruff check .", _RUFF_FAILING, 124, SuccessLevel.FULL_SUCCESS),
        ("ruff check .", _RUFF_FAILING, 137, SuccessLevel.FULL_SUCCESS),
        ("ruff check .", _RUFF_FAILING, -9, SuccessLevel.FULL_SUCCESS),
        ("pytest", _PYTEST_NOTHING_COLLECTED, 5, SuccessLevel.EMPTY_OK),
    ],
    ids=["exit-0", "timeout-124", "killed-137", "signal-negative", "pytest-nothing-collected"],
)
def test_exit_codes_that_do_not_mean_a_failed_check_leave_the_level_alone(
    command: str, stdout: str, exit_code: int, judged: SuccessLevel
) -> None:
    record, _ = _tagged(command, _formatted(command, stdout, exit_code), judged)

    assert record.success_level == judged


def test_a_run_still_going_in_the_background_reports_no_exit_code() -> None:
    still_running = (
        "Command still running after 30s — detached as background job.\n"
        "  pid: 4242\n  command: pytest -q\n\n"
        "Use bash_process_tool(action='wait' or 'output', pid=...) to continue."
    )
    record, before = _tagged("pytest -q", still_running)

    assert record.verification_type == VerificationCategory.TEST
    assert record.success_level == before


def test_a_run_that_finished_inside_the_auto_yield_window_reports_its_exit_code() -> None:
    finished = f"Command finished during auto-yield window (pid=4242).\n{_PYTEST_SUMMARY_FAILING}[exit_code: 1]"
    record, _ = _tagged("pytest -q", finished)

    assert record.success_level == SuccessLevel.FAILURE


@pytest.mark.parametrize("exit_code", [124, -9])
def test_quoted_marker_in_output_cannot_override_the_shells_own(exit_code: int) -> None:
    """The exit line the tool appends is last, so earlier text quoting one does not count."""
    stdout = "[exit_code: 1]\n" + _RUFF_FAILING
    record, _ = _tagged("ruff check .", _formatted("ruff check .", stdout, exit_code), SuccessLevel.FULL_SUCCESS)

    assert record.success_level == SuccessLevel.FULL_SUCCESS


def test_a_run_that_finished_inside_the_auto_yield_window_with_exit_0_passes() -> None:
    finished = "Command finished during auto-yield window (pid=4242).\nAll checks passed!\n[exit_code: 0]"
    record, _ = _tagged("ruff check .", finished, SuccessLevel.FULL_SUCCESS)

    assert record.success_level == SuccessLevel.FULL_SUCCESS


def test_non_verification_command_is_not_touched() -> None:
    """``grep`` exits 1 for no match; only commands that verify code are failed by their exit code."""
    record, _ = _tagged("grep -r needle .", _formatted("grep -r needle .", "", 1), SuccessLevel.FULL_SUCCESS)

    assert record.verification_type is None
    assert record.success_level == SuccessLevel.FULL_SUCCESS


def test_a_later_passing_run_clears_the_failure() -> None:
    failing, _ = _tagged("ruff check .", _formatted("ruff check .", _RUFF_FAILING, 1))
    passing, _ = _tagged("ruff check .", _formatted("ruff check .", _RUFF_PASSING, 0))

    assert failed_verification_types([failing]) == frozenset({VerificationCategory.LINT})
    assert failed_verification_types([failing, passing]) == frozenset()
    assert failed_verification_types([passing, failing]) == frozenset({VerificationCategory.LINT})


@contextmanager
def _guard_environment(budget_verdict: MagicMock) -> Iterator[None]:
    """Neutralise everything around the guard chain that is not under test."""
    tooling = "myrm_agent_harness.agent.middlewares.tooling"
    budget = MagicMock(check_and_truncate=MagicMock(return_value=budget_verdict))
    patches = (
        patch(f"{tooling}._tool_guards.get_context_budget_guard", return_value=budget),
        patch(f"{tooling}._tool_guards.record_decision"),
        patch(f"{tooling}._tool_guards.emit_archive_restore_block_status", new_callable=AsyncMock),
        patch(f"{tooling}._mutation_verifier.record_mutation_result"),
        patch(f"{tooling}._tool_guards.run_content_validation", return_value=None),
        patch(
            "myrm_agent_harness.agent.security.guards.taint_tracker.get_taint_tracker",
            return_value=MagicMock(record_tool_output=MagicMock()),
        ),
        patch(f"{tooling}._tool_guards.check_tool_result_pii", side_effect=lambda result, text, _name: (result, text)),
        patch("myrm_agent_harness.agent.workspace_rules.tracker.check_and_append_rules", return_value=None),
        patch(
            "myrm_agent_harness.agent.hooks.executor.fire_hook",
            new_callable=AsyncMock,
            return_value=MagicMock(blocked=False, all_succeeded=True),
        ),
    )
    with ExitStack() as stack:
        for entered in patches:
            stack.enter_context(entered)
        yield


async def _one_bash_turn(guard: LoopGuard, command: str, text: str, truncated_to: str | None = None) -> CallRecord:
    """Run one bash call through pre-check and the production post-call guard chain.

    ``truncated_to`` makes the context budget cut the result down to that text.
    """
    args: dict[str, object] = {"command": command}
    if truncated_to is None:
        budget_verdict = MagicMock(action=BudgetAction.OK)
    else:
        budget_verdict = MagicMock(action=BudgetAction.TRUNCATED, reason="over budget", content=truncated_to)
    guard.pre_check(_BASH, args)
    record = guard.latest_record()
    assert record is not None
    allow = MagicMock(action=LoopAction.ALLOW, backoff_hint=None)
    with _guard_environment(budget_verdict):
        await run_post_call_guards(
            ToolMessage(content=_envelope(text), name=_BASH, tool_call_id="c"),
            _BASH,
            "c",
            args,
            loop_guard=guard,
            loop_verdict=allow,
            freq_guard=MagicMock(),
            freq_verdict=MagicMock(action=FrequencyAction.ALLOW),
            steering_token=None,
            call_record=record,
        )
    return record


@pytest.mark.asyncio
async def test_failing_lint_run_reaches_the_completion_guard_as_failed_verification() -> None:
    guard = LoopGuard()
    failing = await _one_bash_turn(guard, "ruff check .", _formatted("ruff check .", _RUFF_FAILING, 1))
    assert failed_verification_types([failing]) == frozenset({VerificationCategory.LINT})

    passing = await _one_bash_turn(guard, "ruff check .", _formatted("ruff check .", _RUFF_PASSING, 0))
    assert failed_verification_types([failing, passing]) == frozenset()


@pytest.mark.asyncio
async def test_exit_code_survives_the_context_budget_cutting_the_result() -> None:
    """Truncation keeps the head and tail of output but not necessarily the exit line the tool appended."""
    record = await _one_bash_turn(
        LoopGuard(),
        "ruff check .",
        _formatted("ruff check .", _RUFF_FAILING, 1),
        truncated_to=_RUFF_FAILING.split("\n", 1)[0] + "\n[... output truncated ...]",
    )

    assert failed_verification_types([record]) == frozenset({VerificationCategory.LINT})


async def _repeat_outcomes(command: str, text: str) -> list[str]:
    """What the loop guard does with five identical runs: ``ok`` per run, ``stuck`` where it stops."""
    guard = LoopGuard()
    outcomes: list[str] = []
    for _ in range(5):
        try:
            await _one_bash_turn(guard, command, text)
        except ToolStuckException:
            outcomes.append("stuck")
            break
        outcomes.append("ok")
    return outcomes


@pytest.mark.asyncio
async def test_failing_check_without_keywords_is_handled_like_one_the_judge_already_fails() -> None:
    """The loop guard treats repeating a keyword-free failing check as it treats repeating a full pytest failure."""
    full_failure = _formatted("pytest -q", _PYTEST_FULL_FAILING, 1)
    assert evaluate_success_level(_BASH, full_failure) == SuccessLevel.FAILURE

    reference = await _repeat_outcomes("pytest -q", full_failure)
    assert "stuck" in reference
    assert await _repeat_outcomes("pytest -q", _formatted("pytest -q", _PYTEST_SUMMARY_FAILING, 1)) == reference
    assert await _repeat_outcomes("ruff check .", _formatted("ruff check .", _RUFF_FAILING, 1)) == reference
    assert "stuck" not in await _repeat_outcomes("ruff check .", _formatted("ruff check .", _RUFF_PASSING, 0))
