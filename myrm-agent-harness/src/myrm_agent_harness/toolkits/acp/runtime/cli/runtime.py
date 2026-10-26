"""CLI runtime backend — one external CLI agent process per turn, streamed as RuntimeEvents.

Supports Claude Code (``claude -p --output-format stream-json``), Codex (``codex exec --json``), and any CLI
that prints newline-delimited JSON events. The CLI's own session id is what carries a conversation between turns:
it is stored the moment the CLI announces it and replayed through the CLI's resume syntax (see ``dialect``).

[INPUT]
- toolkits.acp.types::AcpError, AcpErrorCode, BackendCapabilities, CliSessionRecord, CliSessionStore, ContinuityStatus (POS: ACP runtime type definitions layer. Provides all ACP-related core abstractions and data structures, serving as the foundation for the entire ACP module.)
- toolkits.acp.runtime._base::BaseRuntime, build_safe_env (POS: Base class for RuntimeBackend implementations)
- toolkits.acp.runtime.cli.dialect::dialect_for, is_session_id (POS: Per-CLI launch knowledge of CliRuntime)
- toolkits.acp.runtime.cli.failure::classify_failure (POS: Error vocabulary of CliRuntime)
- toolkits.acp.runtime.cli.process::CliLaunchError, CliProcess, spawn_cli_process (POS: Process ownership of CliRuntime)
- toolkits.acp.runtime.cli.session::CliSessionBook (POS: Session continuity state of CliRuntime)
- toolkits.acp.runtime.cli.turn_parser::CliResult, TurnParser (POS: Output parsing of CliRuntime)
- toolkits.code_execution.utils.workspace_path::WorkspacePathResolver (POS: Workspace path resolver with intelligent auto-detection.) [lazy]

[OUTPUT]
- CliRuntime: RuntimeBackend that runs a CLI agent process per turn and continues its conversation across turns

[POS]
CLI runtime backend — decides how a turn is launched, resumed, retried and judged; process and parsing details
live in the sibling modules.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass

from myrm_agent_harness.toolkits.acp.auth._profiles import resolve_cli_args
from myrm_agent_harness.toolkits.acp.runtime._base import BaseRuntime, build_safe_env
from myrm_agent_harness.toolkits.acp.runtime.cli.dialect import CliDialect, dialect_for, is_session_id
from myrm_agent_harness.toolkits.acp.runtime.cli.failure import classify_failure
from myrm_agent_harness.toolkits.acp.runtime.cli.process import CliLaunchError, CliProcess, spawn_cli_process
from myrm_agent_harness.toolkits.acp.runtime.cli.session import CliSessionBook
from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import CliResult, TurnParser
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    BackendCapabilities,
    BackendStatus,
    CliSessionRecord,
    CliSessionStore,
    ContinuityStatus,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)

logger = logging.getLogger(__name__)

# A CLI is silent while one tool call runs (a build, a long test run). Every this many seconds of silence the turn
# says it is still working, so the host does not take the quiet for a hang.
_KEEPALIVE_SECONDS = 15.0

_ACTIVITY_EVENTS = frozenset(
    {
        RuntimeEventType.TEXT_DELTA,
        RuntimeEventType.REASONING_DELTA,
        RuntimeEventType.TOOL_START,
        RuntimeEventType.TOOL_RESULT,
    }
)


def _elapsed(seconds: float) -> str:
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}m {rest:02d}s" if minutes else f"{rest}s"


@dataclass(slots=True)
class _Attempt:
    """What one process run turned out to be; filled in while its events stream."""

    announced: bool = False
    has_text: bool = False
    has_activity: bool = False
    error_streamed: bool = False
    returncode: int = 0
    killed: bool = False
    stderr: str = ""
    notice: str = ""
    result: CliResult | None = None

    def note(self, event: RuntimeEvent) -> None:
        if event.type in _ACTIVITY_EVENTS:
            self.has_activity = True
        if event.type is RuntimeEventType.TEXT_DELTA:
            self.has_text = True
        elif event.type is RuntimeEventType.ERROR:
            self.error_streamed = True

    @property
    def is_stale_resume(self) -> bool:
        """A resumed run the CLI itself rejected before it announced a session or did anything.

        That is the CLI saying it no longer knows the conversation (cleared or expired). A run this runtime
        stopped says nothing about the conversation, and one that announced a session knew it.
        """
        return not self.announced and self.returncode > 0 and not self.killed and not self.has_activity


class CliRuntime(BaseRuntime):
    """RuntimeBackend that runs a CLI process per turn and parses its NDJSON output.

    The prompt reaches the CLI on stdin (``-p``) or as the last argument. A CLI with a dialect (Claude, Codex)
    is resumed from the session it announced earlier, provided the turn starts in the directory that created it;
    with a ``session_store`` that id also survives a restart of the host process. A resume the CLI rejects as
    unknown is retried once as a fresh session in the same turn, and the old id is replaced only once the fresh
    session announced itself. While the CLI prints nothing (one long tool call) the turn reports ``working`` with
    its running time at a fixed interval, so a host that watches for activity does not take the quiet for a hang.
    """

    def __init__(
        self,
        runtime_name: str,
        config: RuntimeConfig,
        *,
        session_store: CliSessionStore | None = None,
    ) -> None:
        super().__init__(runtime_name, config, backend_type="cli")
        self._process: CliProcess | None = None
        self._stop_requested = False
        self._sessions = CliSessionBook(runtime_name, session_store)

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            supports_resume=dialect_for(self._config.command) is not None,
            supports_mcp=False,
            supports_streaming=True,
            supports_tools=False,
        )

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.returncode is None

    async def _do_run_turn(
        self,
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
    ) -> AsyncGenerator[RuntimeEvent]:
        if mcp_servers:
            # CliRuntime 不支持 session-level MCP 注入；pool.run_turn 已拦截，
            # 此处兜底直接调用路径（绕过 pool 时），避免静默失效。
            logger.warning(
                "cli_runtime_mcp_ignored backend=%s mcp_servers=%d reason=unsupported",
                self._name,
                len(mcp_servers),
            )
        command = self._config.command
        if command is None:
            msg = "CliRuntime requires 'command' in RuntimeConfig"
            raise ValueError(msg)

        self._stop_requested = False
        yield create_event(RuntimeEventType.STATUS_UPDATE, session_id, status="starting")

        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import WorkspacePathResolver

        cwd = self._config.cwd or str(WorkspacePathResolver.resolve_workspace_root())
        dialect = dialect_for(command)
        env = {**(dialect.env_defaults if dialect is not None else {}), **build_safe_env(self._config)}
        args = self._launch_args(command, dialect)

        resume_args, notice = await self._resume_args(session_id, cwd, dialect, args)
        if notice is not None:
            yield create_event(RuntimeEventType.STATUS_UPDATE, session_id, status=notice)

        attempt = _Attempt()
        try:
            async with aclosing(
                self._run_attempt(resume_args or args, prompt, session_id, cwd, env, dialect, attempt)
            ) as events:
                async for event in events:
                    yield event

            if resume_args is not None and attempt.is_stale_resume:
                logger.warning(
                    "cli_resume_stale name=%s session=%s code=%d", self._name, session_id, attempt.returncode
                )
                yield create_event(RuntimeEventType.STATUS_UPDATE, session_id, status=ContinuityStatus.SESSION_EXPIRED)
                attempt = _Attempt()
                async with aclosing(self._run_attempt(args, prompt, session_id, cwd, env, dialect, attempt)) as events:
                    async for event in events:
                        yield event
        except CliLaunchError as exc:
            logger.warning("cli_launch_failed name=%s command=%s", self._name, command)
            yield create_event(
                RuntimeEventType.ERROR,
                session_id,
                error=AcpError(AcpErrorCode.BACKEND_NOT_FOUND, str(exc)),
            )
            return

        for event in self._closing_events(attempt, session_id):
            yield event

    def _launch_args(self, command: str, dialect: CliDialect | None) -> list[str]:
        """The command line of a fresh turn: the CLI's launch and permission args, plus what its dialect adds."""
        args = [command, *resolve_cli_args(command, self._config.args, self._config.permission_mode)]
        if "--output-format" in args and "stream-json" in args and "--verbose" not in args:
            args.append("--verbose")
        if dialect is not None:
            args = dialect.with_partial_messages(args)
            args = dialect.with_max_turns(args, self._config.max_turns)
        return args

    async def _resume_args(
        self,
        session_id: str,
        cwd: str,
        dialect: CliDialect | None,
        args: list[str],
    ) -> tuple[list[str] | None, ContinuityStatus | None]:
        """``args`` that continue this session's CLI conversation, and the status to tell when one cannot be.

        A conversation is resumed only from the directory that created it: Claude files sessions per project
        directory, and before v2.1.223 ``--resume`` finds an id only from there.
        """
        if dialect is None or dialect.is_resuming(args):
            return None, None
        record = await self._sessions.recorded(session_id)
        if record is None:
            return None, None
        if record.cwd != cwd:
            logger.info(
                "cli_session_cwd_changed name=%s session=%s recorded_cwd=%s cwd=%s",
                self._name,
                session_id,
                record.cwd,
                cwd,
            )
            return None, ContinuityStatus.WORKSPACE_CHANGED
        resumed = dialect.with_resume(args, record.cli_session_id)
        if resumed is None:
            logger.warning("cli_session_not_resumable name=%s session=%s", self._name, session_id)
            return None, None
        logger.info("cli_resume name=%s session=%s cli_session=%s", self._name, session_id, record.cli_session_id)
        return resumed, None

    async def _run_attempt(
        self,
        args: list[str],
        prompt: str,
        session_id: str,
        cwd: str,
        env: dict[str, str],
        dialect: CliDialect | None,
        attempt: _Attempt,
    ) -> AsyncGenerator[RuntimeEvent]:
        """Run ``args`` once, streaming its events and recording what the run turned out to be in ``attempt``."""
        uses_stdin = "-p" in args
        argv = args if uses_stdin else [*args, prompt]
        parser = TurnParser(session_id)
        started = time.monotonic()
        async with spawn_cli_process(argv, env=env, cwd=cwd, stdin_text=prompt if uses_stdin else None) as process:
            self._process = process
            if self._stop_requested:
                await process.terminate()
            async for line in process.lines(idle_tick=_KEEPALIVE_SECONDS):
                if line is None:
                    yield create_event(
                        RuntimeEventType.STATUS_UPDATE,
                        session_id,
                        status="working",
                        message=_elapsed(time.monotonic() - started),
                    )
                    continue
                for event in parser.feed(line):
                    attempt.note(event)
                    yield event
                announced = parser.take_announced()
                if announced is not None:
                    attempt.announced = True
                    await self._record_session(session_id, announced, cwd, dialect)
            attempt.returncode = await process.wait()
            attempt.killed = process.killed_by_us
            attempt.stderr = process.stderr_text
            attempt.notice = parser.notice
            attempt.result = parser.result

    async def _record_session(self, session_id: str, cli_session_id: str, cwd: str, dialect: CliDialect | None) -> None:
        """Keep the session the CLI just announced — at once, so a turn stopped right after still continues."""
        if dialect is None:
            return
        if not is_session_id(cli_session_id):
            logger.warning("cli_session_unrecognized name=%s session=%s", self._name, session_id)
            return
        self._sessions.remember(session_id, CliSessionRecord(cli_session_id, cwd))
        logger.info("cli_session_announced name=%s session=%s cli_session=%s", self._name, session_id, cli_session_id)
        await self._sessions.persist(session_id)

    def _closing_events(self, attempt: _Attempt, session_id: str) -> list[RuntimeEvent]:
        """The events that end a turn: DONE, or the one ERROR that says why it failed."""
        error = classify_failure(
            result=attempt.result,
            returncode=attempt.returncode,
            stderr=attempt.stderr,
            killed=attempt.killed,
            notice=attempt.notice,
        )
        done = create_event(RuntimeEventType.DONE, session_id, stop_reason="end_turn")
        if error is None:
            return [done]
        if error.code is AcpErrorCode.PROCESS_CRASHED:
            if attempt.error_streamed:
                return []
            if attempt.has_text:
                logger.warning(
                    "cli_process_exited_nonzero name=%s code=%d stderr=%s",
                    self._name,
                    attempt.returncode,
                    attempt.stderr[:200],
                )
                return [done]
        return [create_event(RuntimeEventType.ERROR, session_id, error=error)]

    async def _do_cancel(self, session_id: str) -> None:
        # A stop can land while no process exists yet (the turn is loading its session, or between an attempt
        # and its retry); it then stops the process the moment one is spawned.
        self._stop_requested = True
        if self._process is not None:
            await self._process.terminate()

    async def _do_resume(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def _do_close(self) -> None:
        await self._do_cancel("")
        self._process = None
        self._sessions.clear_memory()

    async def _do_get_status(self) -> BackendStatus:
        if self._process is None:
            return "stopped"
        if self._process.returncode is None:
            return "ready"
        return "error" if self._process.returncode != 0 else "stopped"
