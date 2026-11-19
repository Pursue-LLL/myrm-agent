"""Abstract persistent shell session.

[INPUT]
session.models::SessionConfig, SessionExecutionResult, SessionState (POS: Plain session value types)
session.command_stream::CommandStreamMixin (POS: Command output pump with auto-tee, SSE flood protection, PII scrubbing, cancel/timeout exit)
session.process_tree::kill_process_tree (POS: Stops a shell and every process it started)
session.shell_flavor::get_flavor (POS: Platform-specific shell command formatting)
security.script_armor::prepare_armored_command, sweep_stale_materialized_scripts (POS: Execution security armor: every POSIX command runs from a script file in the workspace)
utils.runtime.cancellation::OperationCancelledError, run_until_cancelled (POS: Abort an await as soon as the request's token is cancelled)

[OUTPUT]
PersistentSession: Abstract base for stateful persistent shell sessions.

[POS]
Abstract persistent shell session base. Manages subprocess lifecycle, state machine, bash syntax pre-check and
script armor (on POSIX each command runs as ``bash <script>`` in a child of the shell, so what it exports or
changes dies with it), and runs the commands of one shell one at a time; the command pump lives in
``CommandStreamMixin``. A command whose request is cancelled is stopped like a timed-out one (tree killed, session
rebuilt on the next command); a command that reaches a shell that died is never replayed.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.code_execution.platform import (
    PlatformInfo,
    detect_platform,
)
from myrm_agent_harness.toolkits.code_execution.security.script_armor import (
    prepare_armored_command,
    sweep_stale_materialized_scripts,
)
from myrm_agent_harness.toolkits.code_execution.session.command_stream import (
    CANCELLED_BEFORE_START,
    CANCELLED_EXIT_CODE,
    CommandStreamMixin,
)
from myrm_agent_harness.toolkits.code_execution.session.models import (
    CommandEnv,
    SessionConfig,
    SessionExecutionResult,
    SessionState,
)
from myrm_agent_harness.toolkits.code_execution.session.process_tree import kill_process_tree
from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import (
    get_flavor,
)
from myrm_agent_harness.utils.runtime.cancellation import OperationCancelledError, run_until_cancelled

if TYPE_CHECKING:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)


def _cancelled_before_start() -> SessionExecutionResult:
    return SessionExecutionResult(False, "", "", CANCELLED_EXIT_CODE, error=CANCELLED_BEFORE_START)


class PersistentSession(CommandStreamMixin, ABC):
    """Abstract base class for persistent shell sessions."""

    def __init__(self, config: SessionConfig, platform_info: PlatformInfo | None = None):
        self.config = config
        self._platform = platform_info or detect_platform()
        self._flavor = get_flavor(self._platform)

        self.process: asyncio.subprocess.Process | None = None
        # ``_lock`` serializes start and close; ``_command_lock`` serializes the commands (see ``execute``).
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._commands_waiting = 0
        self._state = SessionState.IDLE

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    @property
    def _in_use(self) -> bool:
        """Whether a command runs in the shell or waits for it.

        The lock alone does not say: it is free in the moment between one command and the next that waits, and
        while a command that just asked for it has not taken it yet.
        """
        return self._command_lock.locked() or self._commands_waiting > 0

    async def _transit_state(self, new_state: SessionState) -> None:
        """Atomic state transition with logging."""
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        logger.debug(f" Session {self.config.session_id} state: {old_state.name} -> {new_state.name}")

    async def start(self) -> None:
        """Locking entry point for starting the session."""
        if self.is_alive and self._state == SessionState.ACTIVE:
            return

        async with self._lock:
            await self._start_unlocked()

    async def _start_unlocked(self) -> None:
        """Core start logic without lock."""
        if self.is_alive and self._state == SessionState.ACTIVE:
            return

        await self._transit_state(SessionState.STARTING)
        try:
            logger.info(f" Starting persistent session: {self.config.session_id}")
            if not self._platform.is_windows:
                sweep_stale_materialized_scripts(self.config.work_dir)
            self.process = await self._create_process()
            await self._initialize_shell()
            await self._transit_state(SessionState.ACTIVE)
            logger.info(f" Persistent session started: {self.config.session_id}")
        except Exception as e:
            await self._transit_state(SessionState.TERMINATED)
            logger.error(f" Failed to start session: {e}")
            raise

    @abstractmethod
    async def _create_process(self) -> asyncio.subprocess.Process: ...

    async def _initialize_shell(self) -> None:
        init_commands = self._flavor.build_init_commands(
            self.config.work_dir,
            timeout=self.config.timeout,
            max_memory_mb=self.config.max_memory_mb,
        )
        for key, value in self.config.env.items():
            init_commands.append(self._flavor.format_env_set(key, value))

        if not self.process or not self.process.stdin:
            return

        batch = "\n".join(init_commands) + "\n"
        self.process.stdin.write(batch.encode("utf-8", errors="surrogateescape"))
        await self.process.stdin.drain()
        await asyncio.sleep(0.15)

    async def execute(
        self,
        command: str,
        timeout: int | None = None,
        cancel_token: CancellationToken | None = None,
        env: CommandEnv | None = None,
    ) -> SessionExecutionResult:
        """Run ``command`` in the shell once the commands that reached it first are done.

        The shell has one stdin and one stdout and a command owns both from its first byte to its end marker, so the
        commands of a session run one at a time (the parallel sub-agents of a run share its shell). A request that is
        cancelled while its command waits, or before, never starts it (``CANCELLED_BEFORE_START``); one cancelled
        while the command runs stops it (see ``CommandStreamMixin``). A shell that dies under the command is not
        retried, because the command may already have run: the failure is returned and the next command starts a
        new shell. ``env`` is applied around this command only: it is the one way a command's credentials reach a
        shell that was started before them.
        """
        timeout = timeout or self.config.timeout
        try:
            await self._queue_for_shell()
        except OperationCancelledError:
            return _cancelled_before_start()
        try:
            if cancel_token is not None and cancel_token.is_cancelled:
                return _cancelled_before_start()
            start_time = time.perf_counter()
            await self.start()
            result = await self._execute_core(command, timeout, cancel_token, env)
            return dataclasses.replace(result, duration=time.perf_counter() - start_time)
        finally:
            self._command_lock.release()

    async def _queue_for_shell(self) -> None:
        """Take ``_command_lock``, or leave without it when the request is stopped on the way.

        The wait runs as a task so ``run_until_cancelled`` can abandon it at once, and that task can finish (and so
        own the lock) in the very iteration in which its waiter is stopped. A caller that leaves then would keep a
        lock nobody releases and every later command would wait for it, so a lock the wait already took is given
        back, and a wait that has not finished is cancelled before it can take the lock.
        """
        acquire = asyncio.ensure_future(self._command_lock.acquire())
        self._commands_waiting += 1
        try:
            await run_until_cancelled(acquire)
        except BaseException:
            if not acquire.done():
                acquire.cancel()
            elif not acquire.cancelled():
                self._command_lock.release()
            raise
        finally:
            self._commands_waiting -= 1

    async def _precheck_bash_syntax(self, command: str) -> str | None:
        """Return a bash syntax error message when *command* is malformed.

        Spawns ``bash -n`` before the command reaches the persistent shell so
        a broken multi-line block (unbalanced braces, unterminated ``if`` /
        heredoc) is rejected upfront instead of killing the long-lived shell
        process. Best-effort: returns ``None`` on platform mismatch, spawn
        failure or timeout so execution still proceeds and surfaces real errors.
        """
        if self._platform.is_windows:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                "bash",
                "-n",
                "-c",
                command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        except TimeoutError:
            proc.kill()
            await proc.communicate()
            return None
        except OSError:
            return None
        if proc.returncode == 0:
            return None
        detail = stderr.decode("utf-8", errors="replace").strip()
        return detail or f"bash syntax error (exit {proc.returncode})"

    async def _execute_core(
        self,
        command: str,
        timeout: int,
        cancel_token: CancellationToken | None = None,
        env: CommandEnv | None = None,
    ) -> SessionExecutionResult:
        syntax_error = await self._precheck_bash_syntax(command)
        if syntax_error:
            return SessionExecutionResult(False, "", syntax_error, 2, error=syntax_error)

        with contextlib.ExitStack() as armor:
            try:
                cmd_to_run = armor.enter_context(
                    prepare_armored_command(command, self.config.work_dir, self._platform.is_windows)
                )
            except OSError as e:
                # The script is what keeps a command from breaking the shell, so a command without one is not run.
                logger.error("Cannot write the script of a command: %s", e)
                message = (
                    f"The command was not run: its script could not be written ({e.strerror or type(e).__name__})."
                )
                return SessionExecutionResult(False, "", message, 1, error=message)
            return await self._execute_core_stream(cmd_to_run, command, timeout, cancel_token=cancel_token, env=env)

    async def _kill_process_group(self, grace_period: float = 2.0) -> None:
        if not self.process or self.process.pid is None:
            return
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.shield(kill_process_tree(self.process, self._platform.is_windows, grace_period))

    async def _discard_shell(self) -> None:
        """Kill the shell tree and mark the session terminated, so the next command rebuilds a fresh shell."""
        await self._kill_process_group()
        await self._transit_state(SessionState.TERMINATED)

    async def close(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def _close_unlocked(self) -> None:
        if self._state == SessionState.CLOSING:
            return
        await self._transit_state(SessionState.CLOSING)
        try:
            await self._kill_process_group()
        finally:
            self.process = None
            await self._transit_state(SessionState.TERMINATED)

    async def check_health(self) -> bool:
        """Whether the shell is alive and, when no command is using it, answers a trivial command.

        A shell in use is not probed: its commands have a deadline of their own, and a probe could only queue behind
        them while the caller that asked holds up everyone after it. A probe whose request was already stopped never
        ran and learned nothing about the shell, so it counts as healthy: reporting it dead would make the caller
        restart a shell it has no reason to doubt.
        """
        if not self.is_alive:
            return False
        if self._in_use:
            return True
        try:
            res = await self.execute("echo ok", timeout=2)
        except Exception:
            return False
        return res.error == CANCELLED_BEFORE_START or (res.success and "ok" in res.stdout)
