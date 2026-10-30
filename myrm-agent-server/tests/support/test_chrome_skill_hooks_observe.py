"""Unit tests: a turn that never produced its reply is described with what its failed tool steps said."""

from __future__ import annotations

from tests.support.chrome_skill_hooks_observe import _describe_messages

_BLOCKED = "Error: [SECURITY_GUARDRAIL] Execution of 'bash_code_execute_tool' was BLOCKED. (Code: skill_boundary.violation)"


def _assistant(steps: list[dict[str, object]]) -> dict[str, object]:
    return {"role": "assistant", "content": "", "metadata": {"progressSteps": steps}}


def test_a_failed_step_carries_what_the_tool_said() -> None:
    steps: list[dict[str, object]] = [
        {"step_key": "bash_code_execute_tool_tool_error", "status": "error", "error": _BLOCKED},
    ]

    described = _describe_messages([_assistant(steps)])

    assert "skill_boundary.violation" in described
    assert "steps=['bash_code_execute_tool_tool_error']" in described


def test_a_step_that_succeeded_is_named_but_not_dumped() -> None:
    steps: list[dict[str, object]] = [{"step_key": "skill_select_tool_tool", "status": "done", "result": "secret-result-body"}]

    described = _describe_messages([_assistant(steps)])

    assert "skill_select_tool_tool" in described
    assert "secret-result-body" not in described


def test_a_long_failure_is_cut_to_a_bounded_line() -> None:
    steps: list[dict[str, object]] = [{"step_key": "glob_tool_tool_error", "error": "x" * 5000}]

    failed_line = _describe_messages([_assistant(steps)]).splitlines()[-1]

    assert failed_line.startswith("    failed step: ")
    assert len(failed_line) < 1000


def test_a_message_without_steps_is_still_one_line() -> None:
    described = _describe_messages([{"role": "user", "content": "hello", "metadata": {}}])

    assert described.count("\n") == 0
    assert "user: content='hello'" in described
