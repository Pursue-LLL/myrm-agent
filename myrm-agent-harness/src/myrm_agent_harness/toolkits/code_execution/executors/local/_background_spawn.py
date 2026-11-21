"""Background process spawning with sandbox and environment isolation.

[INPUT]
executors.base::ExecutionContext (POS: Code executor base classes)
executors.models::AsyncProcessProtocol (POS: Data models for code execution)
executors.execution_evidence::record_execution (POS: Proof that an agent command launched a process)
code_execution.sandbox::detect_sandbox_provider (POS: Sandbox detection and wrapping)
core.security.process_env::sanitize_env, DEFAULT_CHILD_SAFE_ENV_KEYS (POS: Environment sanitization)
core.security.redact::command_preview (POS: masked, cut command for a log line)
executors.local._background_pty_spawn::try_spawn_background_pty (POS: POSIX PTY spawn adapter)

[OUTPUT]
spawn_background_process: Spawn a sandboxed background process with full-duplex streams. Unless the context is `harness_owned`, it runs under the agent's capability scope and records execution evidence.
PTY-first on POSIX hosts without OS sandbox; falls back to PIPE via `_background_pty_spawn.py`.

[POS]
Background process spawning. Handles sandbox wrapping, environment sanitization,
memory limits, process group management, non-interactive CI-mode environment
defaults (``CI`` / ``NO_COLOR`` / ``DEBIAN_FRONTEND`` / ``PYTHONUNBUFFERED``), a pager
that never waits for a key (``PAGER`` and ``GIT_PAGER`` pinned to ``cat``),
and an 8 MiB ``StreamReader.limit``: the buffer a job may fill before its pipe is
paused, so a burst of output (docker manifests, pytest dumps) does not stall the job
while the reader records it.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path

from myrm_agent_harness.core.security.redact import command_preview
from myrm_agent_harness.toolkits.code_execution.executors.base import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.executors.execution_evidence import record_execution
from myrm_agent_harness.toolkits.code_execution.executors.models import (
    AsyncProcessProtocol,
)

logger = logging.getLogger(__name__)


class _AsyncioProcessWrapper(AsyncProcessProtocol):
    """Adapts ``asyncio.subprocess.Process`` to ``AsyncProcessProtocol``."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    @property
    def stdin(self) -> object:
        return self._proc.stdin

    @property
    def stdout(self) -> object:
        return self._proc.stdout

    @property
    def stderr(self) -> object:
        return self._proc.stderr

    async def wait(self) -> int:
        return await self._proc.wait()

    def terminate(self) -> None:
        import signal

        from myrm_agent_harness.utils import os_compat

        os_compat.kill_process_group(self._proc.pid, signal.SIGTERM)

    def kill(self) -> None:
        from myrm_agent_harness.utils import os_compat

        os_compat.kill_process_group(self._proc.pid, os_compat.SIGKILL)


async def spawn_background_process(
    context: ExecutionContext,
    current_workspace: Path | None,
    resolve_work_dir: Callable[[str, Path | None], Path | None],
    setup_workspace: Callable[[str | None], None],
    venv_path: Path,
    scope_context: Callable[[ExecutionContext], ExecutionContext],
) -> AsyncProcessProtocol:
    """Spawn a long-running background process with full-duplex streams.

    Uses OS-level sandboxing (e.g., bwrap) if available to isolate the process.
    Implements pristine environment sanitization and process tree killing.
    Unless harness-owned, the process runs under the agent's capability scope and counts as execution evidence.

    Args:
        context: Execution context with code, args, env, etc.
        current_workspace: Currently bound workspace path.
        resolve_work_dir: Callable to resolve abstract paths to local paths.
        setup_workspace: Callable to ensure workspace directory exists.
        venv_path: Path to the shared virtual environment.
        scope_context: Narrows the context to the capability handle bound to the running agent.

    Returns:
        AsyncProcessProtocol wrapping the spawned subprocess.
    """
    from myrm_agent_harness.core.context_vars import standing_access_roots
    from myrm_agent_harness.core.security.process_env import (
        DEFAULT_CHILD_SAFE_ENV_KEYS,
        sanitize_env,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox import (
        detect_sandbox_provider,
    )
    from myrm_agent_harness.toolkits.code_execution.sandbox.policy_bridge import (
        build_workspace_sandbox_policy,
    )

    if not context.harness_owned:
        context = scope_context(context)
        record_execution()

    workspace = Path(context.workspace_root) if context.workspace_root else current_workspace
    effective_cwd = resolve_work_dir(context.work_dir, workspace)
    setup_workspace(str(effective_cwd) if effective_cwd else None)

    # Inherit the framework's documented child-safe env allowlist (SSOT) instead of an
    # ad-hoc subset. Dropping the temp vars (TMPDIR/TMP/TEMP) makes the child compute a
    # different ``tempfile.gettempdir()`` than the host, so the PEP 578 audit hook then
    # flags legitimate writes into the real temp dir as "outside allowed workspace".
    base_env = {k: v for k, v in os.environ.items() if k in DEFAULT_CHILD_SAFE_ENV_KEYS}
    env = sanitize_env(base_env)

    if venv_path.exists():
        env["VIRTUAL_ENV"] = str(venv_path)
        venv_bin = str(venv_path / "bin")
        env["PATH"] = venv_bin + os.pathsep + env.get("PATH", "")

    # A job's output is read by a program (the progress parser, the model), not watched on a terminal: tell
    # toolchains to skip colour escapes (which corrupt the progress parser), suppress interactive prompts
    # (apt/debconf hangs are silent killers) and act like a CI run (npm/yarn switch to predictable output).
    # ``setdefault`` keeps a value the host exports; ``context.env``, merged below, still overrides per job.
    env.setdefault("CI", "true")
    env.setdefault("NO_COLOR", "1")
    env.setdefault("FORCE_COLOR", "0")
    env.setdefault("TERM", "dumb")
    env.setdefault("DEBIAN_FRONTEND", "noninteractive")
    env.setdefault("PYTHONUNBUFFERED", "1")
    # On a PTY (the default on POSIX without an OS sandbox) git, man and gh see a real terminal and page their
    # output, so the job would sit at the first page until a key arrives. GIT_PAGER outranks a user's
    # ``core.pager``; PAGER is on the host allow-list, so it is assigned, or a host's ``less`` would reach the job.
    env["PAGER"] = "cat"
    env["GIT_PAGER"] = "cat"

    if context.env:
        env.update(sanitize_env(context.env))

    from myrm_agent_harness.core.security.process_env import (
        is_non_inheritable_env_var,
    )

    # Post-override scrubbing guarantee for background subprocesses
    for k in list(env.keys()):
        if is_non_inheritable_env_var(k):
            env.pop(k, None)

    cmd = context.code
    args = context.args or []

    work_dir_str = str(effective_cwd) if effective_cwd else "/tmp"
    provider, sandbox_status = detect_sandbox_provider()
    preexec_fn: Callable[[], None] | None = None

    if sandbox_status.enabled:
        policy = build_workspace_sandbox_policy(
            work_dir_str,
            readonly=context.readonly_workspace,
            allow_network=context.allow_network,
            granted_roots=standing_access_roots(),
        )
        wrapped_cmd, wrapped_args = provider.wrap_command(cmd, tuple(args), work_dir_str, policy)
        full_cmd_array = [wrapped_cmd, *wrapped_args]
        use_pty = False
    else:
        full_cmd_array = [cmd, *args]
        use_pty = True

        if context.max_memory_mb:
            mem_bytes = context.max_memory_mb * 1024 * 1024

            def _apply_memory_limit() -> None:
                import resource

                with suppress(ValueError, OSError):
                    resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))

            preexec_fn = _apply_memory_limit

    # The issued command, not the shell text built from it: that text starts with a header of its own.
    issued_command = context.original_code or " ".join(full_cmd_array)
    logger.info(f" [LocalExecutor] Spawning background: {command_preview(issued_command, 500)}")

    from myrm_agent_harness.utils import os_compat

    group = os_compat.get_process_group_kwargs()

    if use_pty:
        from myrm_agent_harness.toolkits.code_execution.executors.local._background_pty_spawn import (
            pty_spawn_eligible,
            try_spawn_background_pty,
        )

        if pty_spawn_eligible(sandbox_enabled=False):
            pty_proc = await try_spawn_background_pty(
                full_cmd_array=full_cmd_array,
                effective_cwd=effective_cwd,
                env=env,
                preexec_fn=preexec_fn,
                process_group_kwargs=group,
            )
            if pty_proc is not None:
                return pty_proc
            logger.info(" [LocalExecutor] PTY spawn unavailable; falling back to PIPE")

    # The reader takes the pipe in 64 KiB blocks, so a line of any length is never held whole by the stream.
    # The limit sets how much a job may buffer before the transport pauses its pipe (twice the limit): the
    # default 64 KiB would throttle a job that prints bursts (docker manifest JSON, pytest -vv dumps) while the
    # reader redacts and spills each line. 8 MiB is far above any burst we have seen and tiny next to a job's RSS.
    process = await asyncio.create_subprocess_exec(
        *full_cmd_array,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(effective_cwd) if effective_cwd else None,
        env=env,
        limit=8 * 1024 * 1024,
        # Windows has no fork hook: Popen refuses a preexec_fn there.
        preexec_fn=None if os.name == "nt" else preexec_fn,
        **group,
    )

    return _AsyncioProcessWrapper(process)
