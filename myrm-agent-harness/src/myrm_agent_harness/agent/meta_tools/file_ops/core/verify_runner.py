"""Post-write checks of the file tools: the verify command and the context every check command runs in.

[INPUT]
- toolkits.code_execution.executors.base::CodeExecutor (POS: Code executor base classes.)
- toolkits.code_execution.executors.models::ExecutionContext (POS: How a command is run: directory, workspace root, timeout)
- core.security.redact::command_preview, redact_sensitive_text (POS: masked, cut command for a log line; masked text of an error)

[OUTPUT]
- VerifyOutcome: What the command did: it passed, it failed, or it never ran
- run_verify_command: Runs the command from the workspace root and classifies the outcome
- workspace_command_context: The context that runs a check command from the workspace root (also used by the auto-verify linters)

[POS]
Post-write check of the file tools. A command that ran and exited non-zero judged the file, so the caller undoes the
write. A command that never ran (the command safety check refused it, or the executor raised) says nothing about
the file: the caller keeps the write and tells the model that nothing was checked.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.core.security.redact import command_preview, redact_sensitive_text
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor

logger = logging.getLogger(__name__)

_NOT_RUN_REASON_MAX_CHARS = 300


@dataclass(frozen=True, slots=True)
class VerifyOutcome:
    """What a verify command did."""

    command: str
    verdict: Literal["passed", "failed", "not_run"]
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    reason: str = ""

    @property
    def failed(self) -> bool:
        """The command ran to an exit code that is not success."""
        return self.verdict == "failed"

    @property
    def not_run(self) -> bool:
        """The command never reached a shell."""
        return self.verdict == "not_run"

    def failure_report(self) -> str:
        """Command, exit code and output: what the model needs to fix the file."""
        return (
            f"Command: {self.command}\n"
            f"Exit code: {self.exit_code}\n"
            f"Stdout: {self.stdout}\n"
            f"Stderr: {self.stderr}\n"
            "Please fix the errors and try again."
        )

    def not_run_note(self) -> str:
        """The line appended to a successful write whose check never ran."""
        return f"Verify command did not run: {self.reason}. The change was kept unchecked; run a check yourself."


async def run_verify_command(executor: CodeExecutor, command: str, path: str) -> VerifyOutcome:
    """Run ``command`` from the workspace root, the directory a relative ``path`` of the file tools means.

    ``path`` only names the file in the log lines.
    """
    logger.info("Running verify_command on %s: %s", path, command_preview(command, 200))
    try:
        result = await executor.execute_bash(workspace_command_context(executor, command))
    except Exception as exc:
        # An executor that refuses bash outright (a shadow agent) raises instead of returning a result.
        return _not_run(command, path, f"{type(exc).__name__}: {exc}")

    if result.exit_code is None and not result.success:
        return _not_run(command, path, result.error or result.stderr or "the executor returned no exit code")
    return VerifyOutcome(
        command=command,
        verdict="passed" if result.success else "failed",
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def workspace_command_context(executor: CodeExecutor, command: str, timeout: int | None = None) -> ExecutionContext:
    """Context that runs ``command`` from the workspace root, whatever directory the shell is in.

    A relative ``work_dir`` would resolve against the host process and leave the executor's current workspace
    pointing at it, so the root is given as the abstract ``/workspace`` plus the root the executor is bound to.
    """
    context = ExecutionContext(code=command, enter_work_dir=True, workspace_root=_workspace_root(executor))
    return context if timeout is None else replace(context, timeout=timeout)


def _workspace_root(executor: CodeExecutor) -> str | None:
    try:
        return executor.workspace_path
    except RuntimeError:
        return None


def _not_run(command: str, path: str, reason: str) -> VerifyOutcome:
    short_reason = " ".join(redact_sensitive_text(reason).split())[:_NOT_RUN_REASON_MAX_CHARS]
    logger.warning("verify_command did not run for %s, the change is kept: %s", path, short_reason)
    return VerifyOutcome(command=command, verdict="not_run", reason=short_reason)
