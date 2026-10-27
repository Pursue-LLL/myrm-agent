"""Abstract persistent shell session with auto-recovery.

[INPUT]
session.models::SessionConfig, SessionExecutionResult, SessionState (POS: Plain session value types)
session.command_stream::CommandStreamMixin (POS: Command output pump: execute/stream with auto-tee, SSE flood protection, PII scrubbing, cancel/timeout exit)
session.process_tree::kill_process_tree (POS: Stops a shell and every process it started)
session.shell_flavor::get_flavor (POS: Platform-specific shell command formatting)
security.script_armor::prepare_armored_command, sweep_stale_materialized_scripts (POS: Execution security armor wrapping script materialization, cleanup, and orphan sweeps)

[OUTPUT]
PersistentSession: Abstract base for stateful persistent shell sessions.

[POS]
Abstract persistent shell session base. Manages subprocess lifecycle, state machine, auto-recovery,
bash syntax pre-check and script materialization armor; the command pump lives in ``CommandStreamMixin``.
A command whose request is cancelled is stopped like a timed-out one (tree killed, session rebuilt on the next command).
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

if TYPE_CHECKING:
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)


class PersistentSession(CommandStreamMixin, ABC):
    """Abstract base class for persistent shell sessions."""

    _SESSION_DIED_SENTINEL = "Session process ended unexpectedly"

    def __init__(self, config: SessionConfig, platform_info: PlatformInfo | None = None):
        self.config = config
        self._platform = platform_info or detect_platform()
        self._flavor = get_flavor(self._platform)

        self.process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()
        self._state = SessionState.IDLE
        self._state_changed = asyncio.Event()

        self._consecutive_failures = 0
        self._last_returncode: int | None = None

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def _transit_state(self, new_state: SessionState) -> None:
        """Atomic state transition with logging."""
        old_state = self._state
        if old_state == new_state:
            return
        self._state = new_state
        self._state_changed.set()
        self._state_changed.clear()
        logger.debug(f" Session {self.config.session_id} state: {old_state.name} -> {new_state.name}")

    async def _ensure_active(self) -> None:
        """Ensure the session is active, waiting for it if it's currently starting/recovering."""
        while True:
            if self._state == SessionState.ACTIVE and self.is_alive:
                return

            if self._state in (
                SessionState.IDLE,
                SessionState.TERMINATED,
                SessionState.CLOSING,
            ) or (self._state == SessionState.ACTIVE and not self.is_alive):
                await self.start()
                return

            if self._state in (SessionState.STARTING, SessionState.RECOVERING):
                await self._state_changed.wait()
                continue

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
                sweep_stale_materialized_scripts("/tmp")
            self.process = await self._create_process()
            await self._initialize_shell()
            self._consecutive_failures = 0
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
        """Execute a command with auto-recovery.

        When ``cancel_token`` is cancelled the command is stopped (see ``CommandStreamMixin``); a request that
        was already cancelled never starts it. ``env`` is applied around this command only: it is the one way a
        command's credentials reach a shell that was started before them.
        """
        timeout = timeout or self.config.timeout
        start_time = time.perf_counter()

        if cancel_token is not None and cancel_token.is_cancelled:
            return SessionExecutionResult(False, "", "", CANCELLED_EXIT_CODE, error=CANCELLED_BEFORE_START)

        await self._ensure_active_unlocked()
        result = await self._execute_core(command, timeout, cancel_token, env)

        # Auto-recovery logic
        if self._should_recover(result):
            result = await self._recover_and_retry(command, timeout, cancel_token, env)

        return dataclasses.replace(result, duration=time.perf_counter() - start_time)

    async def _ensure_active_unlocked(self) -> None:
        """Unlocked version of ensure_active."""
        while True:
            if self._state == SessionState.ACTIVE and self.is_alive:
                return
            if self._state in (
                SessionState.IDLE,
                SessionState.TERMINATED,
                SessionState.CLOSING,
            ) or (self._state == SessionState.ACTIVE and not self.is_alive):
                await self._start_unlocked()
                return
            if self._state in (SessionState.STARTING, SessionState.RECOVERING):
                return

    def _should_recover(self, result: SessionExecutionResult) -> bool:
        return (
            result.error is not None and self._SESSION_DIED_SENTINEL in result.error and self._consecutive_failures <= 1
        )

    async def _recover_and_retry(
        self,
        command: str,
        timeout: int,
        cancel_token: CancellationToken | None = None,
        env: CommandEnv | None = None,
    ) -> SessionExecutionResult:
        await self._transit_state(SessionState.RECOVERING)
        logger.warning(f" Recovering session {self.config.session_id} after crash...")
        try:
            await self._kill_process_group()
            self.process = await self._create_process()
            await self._initialize_shell()
            self._consecutive_failures = 0
            await self._transit_state(SessionState.ACTIVE)
            return await self._execute_core(command, timeout, cancel_token, env)
        except Exception as e:
            logger.error("Session recovery failed: %s", e)
            await self._transit_state(SessionState.TERMINATED)
            return SessionExecutionResult(False, "", "", 1, error="Recovery failed")

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

        with prepare_armored_command(
            command,
            work_dir=self.config.work_dir,
            is_windows=self._platform.is_windows,
        ) as cmd_to_run:
            is_armored = getattr(cmd_to_run, "is_armored", False)
            return await self._execute_core_stream(
                cmd_to_run,
                command,
                timeout,
                is_armored=is_armored,
                cancel_token=cancel_token,
                env=env,
            )

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
        if not self.is_alive:
            return False
        try:
            res = await self.execute("echo ok", timeout=2)
            return res.success and "ok" in res.stdout
        except Exception:
            return False
