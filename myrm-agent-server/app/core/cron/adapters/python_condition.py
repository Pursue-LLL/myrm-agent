"""Sandboxed Python pre-flight condition execution.

Runs a user-provided Python script in an isolated subprocess before a job and reads its verdict:

- prints `[SKIP]` or ends with `{"action": "skip"}`: the run is skipped (no LLM wake-up);
- any other output: the standard output is returned as `injected_context`;
- exits non-zero, times out, cannot start or writes more than 5 MiB: `PreFlightConditionError`, so the run fails and
  the user hears of it.

[INPUT]
- toolkits.cron.protocols::PreFlightCondition, PreFlightConditionError (POS: Protocols for the cron toolkit.)
- toolkits.cron.types::CronJob (POS: In-memory representation of a cron job.)
- myrm_agent_harness.api::redact_sensitive_text (POS: Masks credentials in text before it is stored or shown.)
- myrm_agent_harness.api::communicate_bounded (POS: Reads a child process's stdout and stderr with a cap on each and
  stops it through the caller on a deadline or a cancel.)
- toolkits.code_execution.session.process_tree::kill_process_tree (POS: Stops a process and its whole tree, escalating from
  terminate to kill after a grace period.)
- utils.os_compat::IS_WIN, get_process_group_kwargs, kill_spawned_group (POS: Unified abstractions for POSIX/Windows
  differences.)

[OUTPUT]
- SandboxedPythonCondition: Executes Python scripts in a sandboxed subprocess.

[POS]
Sandboxed Python condition execution. Implements PreFlightCondition.
"""

import asyncio
import json
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from myrm_agent_harness.api import (
    EnvInheritPolicy,
    build_isolated_child_env,
    communicate_bounded,
    redact_sensitive_text,
)
from myrm_agent_harness.toolkits.code_execution.session.process_tree import kill_process_tree
from myrm_agent_harness.toolkits.cron.protocols import PreFlightCondition, PreFlightConditionError
from myrm_agent_harness.toolkits.cron.types import CronJob
from myrm_agent_harness.utils.os_compat import IS_WIN, get_process_group_kwargs, kill_spawned_group

logger = logging.getLogger(__name__)

# The reason reaches the run history and the delivery channels, so it is one short line with credentials masked.
_MAX_REASON_CHARS = 300
# Bounds the masking work on a very long line.
_MAX_RAW_CHARS = 1000
# A probe has no state to flush: after the deadline or a cancel, the script gets this long to stop on a polite signal
# and what is left of its process tree this long again before it is killed, so the extra wait is at most twice this.
# On POSIX a background command that init has adopted is in no tree, so the tree stop does not wait for it: it gets the
# group's polite signal only if the script is not yet reaped, and the group kill ends it no later than the stop returns.
_KILL_GRACE_SECONDS = 1.0
# What the script wrote becomes the job's prompt or its delivered text, so a script that fills this much is broken. It
# fails the run instead of being cut: the verdict is the last line, which a cut would drop.
_MAX_OUTPUT_MIB = 5
_MAX_OUTPUT_BYTES = _MAX_OUTPUT_MIB * 1024 * 1024


@dataclass(frozen=True, slots=True)
class _ScriptRun:
    returncode: int
    stdout: str
    stderr: str
    truncated: bool


class SandboxedPythonCondition(PreFlightCondition):
    """Executes a Python script in an isolated subprocess with a strict timeout.

    If the script prints `[SKIP]` or `{"action": "skip"}`, aborts job execution.
    Otherwise, the entire stdout is collected and returned as `injected_context`.
    A script that crashes, times out, cannot start or writes more than 5 MiB raises `PreFlightConditionError`.
    """

    def __init__(self, timeout_seconds: int = 10) -> None:
        self.timeout_seconds = timeout_seconds

    async def evaluate(self, job: CronJob) -> tuple[bool, str]:
        script = (job.pre_condition_script or "").strip()
        if not script:
            return True, ""

        logger.debug("Executing pre-flight condition script for job %s", job.id)

        try:
            run = await self._execute(script)
        except TimeoutError:
            logger.warning("Pre-flight condition for job %s timed out after %ds", job.id, self.timeout_seconds)
            raise PreFlightConditionError(f"timed out after {self.timeout_seconds}s") from None
        except Exception as exc:
            logger.error("Pre-flight condition for job %s could not run: %s", job.id, exc)
            raise PreFlightConditionError(f"could not run the script ({type(exc).__name__})") from exc

        if run.returncode != 0:
            logger.warning("Pre-flight condition for job %s failed with exit code %d: %s", job.id, run.returncode, run.stderr)
            reason = _failure_reason(run.stderr)
            raise PreFlightConditionError(f"exit code {run.returncode}: {reason}" if reason else f"exit code {run.returncode}")

        if run.truncated:
            logger.warning("Pre-flight condition for job %s wrote more than %d MiB", job.id, _MAX_OUTPUT_MIB)
            raise PreFlightConditionError(f"wrote more than {_MAX_OUTPUT_MIB} MiB of output")

        return _read_verdict(run.stdout)

    async def _execute(self, script: str) -> _ScriptRun:
        """Run the script in a subprocess without host secrets; returns its exit code and the output it wrote."""
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
                # A session of its own, so the cleanup below can signal the script's whole process group.
                **get_process_group_kwargs(),
            )
            # A deadline or a cancel only stops the wait: the script and what it started keep running, and a
            # descendant holding the pipes would keep `wait()` from returning.
            output = await communicate_bounded(
                proc,
                timeout=self.timeout_seconds,
                on_abort=lambda: _stop_script(proc),
                max_bytes=_MAX_OUTPUT_BYTES,
            )
            return _ScriptRun(
                returncode=await proc.wait(),
                stdout=output.stdout.decode(errors="replace").strip(),
                stderr=output.stderr.decode(errors="replace").strip(),
                truncated=output.truncated,
            )
        finally:
            if script_path is not None:
                script_path.unlink(missing_ok=True)


async def _stop_script(proc: asyncio.subprocess.Process) -> None:
    """Stop the script and everything it started, also when the script exited first.

    The process tree is read from the script, so it reaches what moved to another session while the script ran, and it
    asks everything to stop before forcing it. It reaches nothing once the script has exited, and a background command
    that ignores the polite signal outlives it. Both are still in the script's process group, which is named after the
    script's pid, so the group is killed last. Not found: a process that left the group and was adopted by init before
    the stop. Windows has no such group, and its group stop needs the script to still exist, so the tree stop is all
    there is there.
    """
    await kill_process_tree(proc, IS_WIN, _KILL_GRACE_SECONDS)
    if not IS_WIN:
        kill_spawned_group(proc.pid)


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
