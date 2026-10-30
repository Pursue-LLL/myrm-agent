"""Sandboxed Python pre-flight condition execution.

Runs a user-provided Python script in an isolated subprocess before a job and reads its verdict:

- prints `[SKIP]` or ends with `{"action": "skip"}`: the run is skipped (no LLM wake-up);
- any other output: the standard output is returned as `injected_context`;
- exits non-zero, times out or cannot start: `PreFlightConditionError`, so the run fails and the user hears of it.

[INPUT]
- toolkits.cron.protocols::PreFlightCondition, PreFlightConditionError (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob (POS: In-memory representation of a cron job.)
- myrm_agent_harness.api::redact_sensitive_text (POS: Masks credentials in text before it is stored or shown.)
- toolkits.code_execution.session.process_tree::kill_process_tree (POS: Stops a process and its whole tree, escalating from
  terminate to kill after a grace period.)
- utils.os_compat::IS_WIN (POS: Unified abstractions for POSIX/Windows differences.)

[OUTPUT]
- SandboxedPythonCondition: Executes Python scripts in a sandboxed subprocess.

[POS]
Sandboxed Python condition execution. Implements PreFlightCondition.
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

from myrm_agent_harness.api import (
    EnvInheritPolicy,
    build_isolated_child_env,
    redact_sensitive_text,
)
from myrm_agent_harness.toolkits.code_execution.session.process_tree import kill_process_tree
from myrm_agent_harness.toolkits.cron.protocols import PreFlightCondition, PreFlightConditionError
from myrm_agent_harness.toolkits.cron.types import CronJob
from myrm_agent_harness.utils.os_compat import IS_WIN

logger = logging.getLogger(__name__)

# The reason reaches the run history and the delivery channels, so it is one short line with credentials masked.
_MAX_REASON_CHARS = 300
# Bounds the masking work on a very long line.
_MAX_RAW_CHARS = 1000
# A probe has no state to flush: after the deadline or a cancel the script and everything it started get this long
# to stop on a polite signal and as long again after the forced kill, so the extra wait is at most twice this.
_KILL_GRACE_SECONDS = 1.0


class SandboxedPythonCondition(PreFlightCondition):
    """Executes a Python script in an isolated subprocess with a strict timeout.

    If the script prints `[SKIP]` or `{"action": "skip"}`, aborts job execution.
    Otherwise, the entire stdout is collected and returned as `injected_context`.
    A script that crashes, times out or cannot start raises `PreFlightConditionError`.
    """

    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    async def evaluate(self, job: CronJob) -> tuple[bool, str]:
        script = (job.pre_condition_script or "").strip()
        if not script:
            return True, ""

        logger.debug("Executing pre-flight condition script for job %s", job.id)

        try:
            returncode, stdout, stderr = await self._execute(script)
        except TimeoutError:
            logger.warning("Pre-flight condition for job %s timed out after %ds", job.id, self.timeout_seconds)
            raise PreFlightConditionError(f"timed out after {self.timeout_seconds}s") from None
        except Exception as exc:
            logger.error("Pre-flight condition for job %s could not run: %s", job.id, exc)
            raise PreFlightConditionError(f"could not run the script ({type(exc).__name__})") from exc

        if returncode != 0:
            logger.warning("Pre-flight condition for job %s failed with exit code %d: %s", job.id, returncode, stderr)
            reason = _failure_reason(stderr)
            raise PreFlightConditionError(f"exit code {returncode}: {reason}" if reason else f"exit code {returncode}")

        return _read_verdict(stdout)

    async def _execute(self, script: str) -> tuple[int, str, str]:
        """Run the script in a subprocess without host secrets; returns its exit code, stdout and stderr."""
        script_path: Path | None = None
        try:
            with NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                script_path = Path(f.name)
                f.write(script)

            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=build_isolated_child_env(inherit_policy=EnvInheritPolicy.CORE),
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout_seconds)
            except BaseException:
                # A deadline or a cancel only stops the wait: the script and what it started keep running, and a
                # descendant holding the pipes would keep `wait()` from returning. Stop the whole tree first.
                await asyncio.shield(kill_process_tree(proc, IS_WIN, _KILL_GRACE_SECONDS))
                raise
            returncode = await proc.wait()
            return returncode, stdout.decode(errors="replace").strip(), stderr.decode(errors="replace").strip()
        finally:
            if script_path is not None:
                script_path.unlink(missing_ok=True)


def _read_verdict(stdout: str) -> tuple[bool, str]:
    """`(False, "")` when the script asks to skip the run, otherwise `(True, stdout)` as the injected context."""
    lines = stdout.splitlines()
    if any(line.strip() == "[SKIP]" for line in lines):
        return False, ""

    if lines:
        last_line = lines[-1].strip()
        if last_line.startswith("{") and last_line.endswith("}"):
            try:
                if json.loads(last_line).get("action") == "skip":
                    return False, ""
            except json.JSONDecodeError:
                pass

    return True, stdout


def _failure_reason(stderr: str) -> str:
    """The last stderr line, where a traceback names the exception, as one bounded line with credentials masked."""
    lines = stderr.splitlines()
    if not lines:
        return ""
    line = redact_sensitive_text(lines[-1].strip()[:_MAX_RAW_CHARS])
    return line if len(line) <= _MAX_REASON_CHARS else f"{line[: _MAX_REASON_CHARS - 1]}…"
