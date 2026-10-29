"""Build the tool-call records the completion guard reads, one line per call.

[INPUT]
- myrm_agent_harness.agent.security.guards.loop_guard::CallRecord, SuccessLevel, VerificationCategory (POS: one recorded tool call)

[OUTPUT]
- OK / FAIL / EMPTY: the success levels a call ends with
- call / write / shell / unit_tests / lint: a call by tool and target, a file write, a shell command, a test run, a lint run

[POS]
Pytest-only helper shared by the completion-guard rule, checklist and guard tests, so each test states the trace
it is about and not how a record is assembled.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    VerificationCategory,
)

OK = SuccessLevel.FULL_SUCCESS
FAIL = SuccessLevel.FAILURE
EMPTY = SuccessLevel.EMPTY_OK


def call(
    tool: str,
    target: str,
    level: SuccessLevel = OK,
    verification: VerificationCategory | None = None,
) -> CallRecord:
    """One recorded call; ``target`` is the path of a file tool or the command of a shell."""
    args: dict[str, object] = {"command": target} if tool == "bash_code_execute_tool" else {"path": target}
    return CallRecord(
        tool_name=tool,
        args_hash=f"{tool}:{target}",
        args=args,
        success_level=level,
        verification_type=verification,
    )


def write(path: str, level: SuccessLevel = OK) -> CallRecord:
    return call("file_write_tool", path, level)


def shell(
    command: str,
    level: SuccessLevel = OK,
    verification: VerificationCategory | None = None,
) -> CallRecord:
    return call("bash_code_execute_tool", command, level, verification)


def unit_tests(level: SuccessLevel = OK) -> CallRecord:
    return shell("pytest", level, VerificationCategory.TEST)


def lint(level: SuccessLevel = OK) -> CallRecord:
    return shell("ruff check .", level, VerificationCategory.LINT)
