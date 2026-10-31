"""Python script subprocess execution with sandbox and timeout.

[INPUT]
utils.runtime.cancel_hook::DeadlineCut, cut_deadline_on_cancel (POS: end a timeout scope as soon as the request token is cancelled)
executors.base::ExecutionContext (POS: Code executor base classes)
executors.base::ExecutionResult (POS: Code executor base classes)
executors.common::parse_execution_output (POS: Shared execution utilities)
code_execution.sandbox::detect_sandbox_provider (POS: Sandbox detection and wrapping)
core.security.process_env::sanitize_env, is_non_inheritable_env_var (POS: Environment sanitization)
core.security.bounded_communicate::communicate_bounded (POS: communicate() with a cap on each pipe, stopping the process through the caller's on_abort)
utils.os_compat::get_process_group_kwargs, kill_spawned_group (POS: Unified abstractions for POSIX/Windows differences (file locks, process groups))

[OUTPUT]
run_python_subprocess: Execute a Python script in a sandboxed subprocess with timeout.

[POS]
Python subprocess execution. Handles environment preparation, sandbox wrapping,
graceful timeout (SIGTERM → SIGKILL of the whole process group, including what the script left running), cancel-aware
stop (a cancelled request ends the script like a timeout, but reports "cancelled"), and output parsing for Python code
execution. Each pipe is read up to a cap (stdout has the headroom for the wrapper's encoded result, stderr is raw
text), so a script that never stops writing cannot grow the host's memory.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import traceback
from pathlib import Path

from myrm_agent_harness.core.security.bounded_communicate import communicate_bounded
from myrm_agent_harness.toolkits.code_execution.executors.base import (
    ExecutionContext,
    ExecutionResult,
)
from myrm_agent_harness.toolkits.code_execution.executors.common import (
    parse_execution_output,
)
from myrm_agent_harness.utils.os_compat import SIGKILL, get_process_group_kwargs, kill_spawned_group
from myrm_agent_harness.utils.runtime.cancel_hook import DeadlineCut, cut_deadline_on_cancel

logger = logging.getLogger(__name__)

# The wrapper prints its result with json.dumps (ensure_ascii), which spells one character with up to 12 bytes: a
# character outside the BMP becomes a surrogate pair of \uXXXX escapes. The slack holds the rest of the JSON.
_JSON_BYTES_PER_CHAR = 12
_RESULT_SLACK_BYTES = 64 * 1024


def _stdout_limit(max_output_bytes: int) -> int:
    """Bytes of the stdout pipe that always hold the whole result of a script whose captured stdout stays within the wrapper's cap.

    The wrapper bounds only the stdout it captures, counted in characters. What a script writes straight to the file
    descriptor reaches the pipe unbounded, so the host stops reading into memory at this size.
    """
    return max_output_bytes * _JSON_BYTES_PER_CHAR + _RESULT_SLACK_BYTES


def _stderr_limit(max_output_bytes: int) -> int:
    """Bytes of the stderr pipe the host keeps: raw text the script wrote, plus room for a traceback.

    The wrapper's result, which needs the stdout headroom, never travels on this pipe.
    """
    return max_output_bytes + _RESULT_SLACK_BYTES


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """Stop the child and everything in its process group: SIGTERM, then SIGKILL for what is left after 2 s.

    The group is addressed by the child's pid, so the SIGKILL also reaches what the child started and left running
    after it had exited. It is the only stop for both the deadline and a cancel, run once through ``on_abort``. Never
    raises: cleanup failures must not mask the original timeout/cancel outcome.
    """
    try:
        if process.returncode is None:
            kill_spawned_group(process.pid, signal.SIGTERM)
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(process.wait(), timeout=2)
        kill_spawned_group(process.pid, SIGKILL)
    except Exception as e:
        logger.warning("Process group cleanup failed: %s", e)


async def run_python_subprocess(
    script_path: Path,
    timeout: int,
    python_executable: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    allow_network: bool = True,
    context: ExecutionContext | None = None,
    *,
    max_output_bytes: int,
) -> ExecutionResult:
    """Execute a Python script via subprocess with sandbox and timeout.

    Args:
        script_path: Path to the Python script to execute.
        timeout: Timeout in seconds.
        python_executable: Path to the Python interpreter.
        cwd: Working directory.
        env: User-defined environment variables.
        allow_network: Whether to allow network access.
        context: Optional execution context for readonly_workspace flag.
        max_output_bytes: The script's cap on captured stdout characters, as given to ``generate_wrapper_script``.

    Returns:
        Execution result with stdout, stderr, exit code.
    """
    try:
        from myrm_agent_harness.core.security.process_env import (
            is_non_inheritable_env_var,
            sanitize_env,
        )
        from myrm_agent_harness.toolkits.code_execution.sandbox import (
            detect_sandbox_provider,
        )
        from myrm_agent_harness.toolkits.code_execution.sandbox.policy_bridge import (
            build_workspace_sandbox_policy,
        )

        process_env = sanitize_env(os.environ.copy())
        # Strip hostile parent PYTHONPATH to prevent cross-venv binary mismatch & ModuleNotFoundError traps
        process_env.pop("PYTHONPATH", None)

        # Inject venv site-packages into PYTHONPATH if python_executable is from a venv
        python_exec_path = Path(python_executable)
        venv_root = python_exec_path.parent.parent
        venv_lib = venv_root / "lib"
        extra_paths = []
        if venv_lib.exists():
            for sp in venv_lib.glob("python*/site-packages"):
                extra_paths.append(str(sp))

        python_path = os.pathsep.join(extra_paths) if extra_paths else ""

        if env:
            sanitized_user_env = sanitize_env(env)
            user_pythonpath = sanitized_user_env.pop("PYTHONPATH", None)
            process_env.update(sanitized_user_env)
            if user_pythonpath:
                python_path = f"{user_pythonpath}{os.pathsep}{python_path}" if python_path else user_pythonpath
            logger.debug(f" User env vars: {list(env.keys())}")

        if python_path:
            process_env["PYTHONPATH"] = python_path
        else:
            process_env.pop("PYTHONPATH", None)

        # Post-override scrubbing guarantee: strip any non-inheritable host secrets (Codex #38941)
        # Verified PTC orchestration sessions carry their stub dir on PYTHONPATH
        # (allowed by sanitize_env); the scrub below must not remove it, or
        # `import myrm_tools` fails inside orchestration scripts. Same marker
        # heuristic as env_isolation._is_ptc_orchestration_env.
        ptc_session = "_MYRM_PTC_SOCKET" in process_env or "_MYRM_PTC_PORT" in process_env
        for k in list(process_env.keys()):
            if k == "PYTHONPATH" and ptc_session:
                continue
            if is_non_inheritable_env_var(k):
                process_env.pop(k, None)

        logger.info(f" [LocalExecutor] Using Python: {python_executable}")

        work_dir_str = str(cwd) if cwd else "/tmp"
        provider, sandbox_status = detect_sandbox_provider()

        if sandbox_status.enabled:
            policy = build_workspace_sandbox_policy(
                work_dir_str,
                readonly=bool(context and context.readonly_workspace),
                allow_network=allow_network,
            )
            wrapped_cmd, wrapped_args = provider.wrap_command(
                python_executable, (str(script_path),), work_dir_str, policy
            )
            full_cmd_executable = wrapped_cmd
            full_cmd_args = wrapped_args
        else:
            full_cmd_executable = python_executable
            full_cmd_args = (str(script_path),)

        process = await asyncio.create_subprocess_exec(
            full_cmd_executable,
            *full_cmd_args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=process_env,
            **get_process_group_kwargs(),
        )

        cut = DeadlineCut()
        try:
            async with (
                asyncio.timeout(timeout) as deadline,
                cut_deadline_on_cancel(context.cancel_token if context else None, deadline, cut),
            ):
                # The surrounding scope owns the deadline and its early cut on cancel; the equal timeout is only
                # there because the primitive takes one.
                piped = await communicate_bounded(
                    process,
                    timeout=timeout,
                    on_abort=lambda: _kill_process_tree(process),
                    max_bytes=_stdout_limit(max_output_bytes),
                    stderr_max_bytes=_stderr_limit(max_output_bytes),
                )
        except TimeoutError:
            if cut.by_cancel:
                return ExecutionResult(
                    success=False,
                    error="Cancelled: the run was stopped while this script was running, so the script was terminated.",
                    stderr="Cancelled",
                )
            return ExecutionResult(
                success=False,
                error=f"Execution timed out after {timeout}s",
                stderr="Timeout",
            )

        stdout = piped.stdout.decode("utf-8", errors="replace")
        stderr = piped.stderr.decode("utf-8", errors="replace")
        exit_code = process.returncode or 0

        output = parse_execution_output(stdout, stderr, exit_code)
        result_stderr = output.stderr
        if piped.truncated:
            note = (
                "[Output limit reached: the script wrote more than the host keeps from a pipe; the rest was discarded]"
            )
            result_stderr = f"{result_stderr}\n{note}" if result_stderr else note

        return ExecutionResult(
            success=output.success,
            result=output.result,
            stdout=output.stdout,
            stderr=result_stderr,
            error=output.error,
            exit_code=exit_code,
        )

    except Exception as e:
        traceback.print_exc()
        return ExecutionResult(
            success=False,
            error=f"{type(e).__name__}: {e!s}",
            stderr=str(e),
        )
