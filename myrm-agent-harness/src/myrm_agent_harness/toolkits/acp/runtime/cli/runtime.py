"""CLI runtime backend — spawns a CLI agent process and parses NDJSON output.

Supports Claude CLI (``claude --output-format stream-json``), Codex CLI,
Gemini CLI, and any CLI tool that outputs newline-delimited JSON events.

[INPUT]
- toolkits.acp.types::AcpError, AcpErrorCode, BackendCapabilities, CliSessionRecord, CliSessionStore (POS: ACP runtime type definitions layer. Provides all ACP-related core abstractions and data structures, serving as the foundation for the entire ACP module.)
- toolkits.acp.runtime._base::BaseRuntime, build_safe_env (POS: Base class for RuntimeBackend implementations)
- toolkits.acp.runtime.cli.parser::parse_json_line, parse_ndjson_line (POS: Shared NDJSON event parsers for CLI and SDK runtimes)
- toolkits.acp.runtime.cli.session::CliSessionBook (POS: Session continuity state of CliRuntime. Owns the bounded in-memory record cache and every store interaction)
- toolkits.acp.runtime.cli.spawn_hints::format_cli_spawn_failure_message (POS: ACP runtime spawn diagnostics. Keeps CliRuntime error messages actionable without product-layer imports)
- toolkits.code_execution.utils.workspace_path::WorkspacePathResolver (POS: Workspace path resolver with intelligent auto-detection.)
- utils.os_compat::get_process_group_kwargs, kill_process_group (POS: Provides unified abstractions for POSIX/Windows differences (file locks, process groups) to ensure 100% native execution across all platforms) [lazy]

[OUTPUT]
- CliRuntime: RuntimeBackend that spawns a CLI process and parses NDJSO...

[POS]
CLI runtime backend — spawns a CLI agent process and parses NDJSON output.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import AsyncIterator

from myrm_agent_harness.toolkits.acp.auth._profiles import resolve_cli_args
from myrm_agent_harness.toolkits.acp.runtime._base import BaseRuntime, build_safe_env
from myrm_agent_harness.toolkits.acp.runtime.cli.parser import parse_json_line, parse_ndjson_line
from myrm_agent_harness.toolkits.acp.runtime.cli.session import CliSessionBook
from myrm_agent_harness.toolkits.acp.types import (
    AcpError,
    AcpErrorCode,
    BackendCapabilities,
    BackendStatus,
    CliSessionRecord,
    CliSessionStore,
    McpServerConfig,
    RuntimeConfig,
    RuntimeEvent,
    RuntimeEventType,
    create_event,
)

logger = logging.getLogger(__name__)


_RESUME_COMMANDS = frozenset({"claude"})


def _supports_resume(command: str) -> bool:
    """Check if a CLI command supports the ``--resume`` flag."""
    base = os.path.basename(command)
    return base in _RESUME_COMMANDS


class CliRuntime(BaseRuntime):
    """RuntimeBackend that spawns a CLI process and parses NDJSON output.

    The CLI process receives the prompt via stdin (or as a trailing argument)
    and emits newline-delimited JSON events to stdout. Each JSON line is parsed
    and converted into a RuntimeEvent.

    For CLI tools that support session resume (e.g. Claude CLI ``--resume``),
    the runtime captures the session ID from ``result`` events and injects
    ``--resume <id>`` on subsequent calls to the same session, provided the
    turn starts in the directory that created it. With a ``session_store`` the
    id also survives a restart of the host process. A crash on resume (no
    output produced) drops the stale session ID so the next call degrades to
    a fresh session.
    """

    def __init__(
        self,
        runtime_name: str,
        config: RuntimeConfig,
        *,
        session_store: CliSessionStore | None = None,
    ) -> None:
        super().__init__(runtime_name, config, backend_type="cli")
        self._process: asyncio.subprocess.Process | None = None
        self._sessions = CliSessionBook(runtime_name, session_store)

    @property
    def capabilities(self) -> BackendCapabilities:
        can_resume = self._config.command is not None and _supports_resume(self._config.command)
        return BackendCapabilities(
            supports_resume=can_resume,
            supports_mcp=False,
            supports_streaming=True,
            supports_tools=False,
        )

    @property
    def is_alive(self) -> bool:
        if self._process is None:
            return False
        return self._process.returncode is None

    async def _do_run_turn(
        self,
        prompt: str,
        session_id: str,
        *,
        mcp_servers: list[McpServerConfig] | None = None,
    ) -> AsyncIterator[RuntimeEvent]:
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

        yield create_event(
            RuntimeEventType.STATUS_UPDATE,
            session_id,
            status="starting",
            message=f"Spawning CLI process: {command}",
        )

        from myrm_agent_harness.toolkits.code_execution.utils.workspace_path import (
            WorkspacePathResolver,
        )

        safe_env = build_safe_env(self._config)
        cwd = self._config.cwd or str(WorkspacePathResolver.resolve_workspace_root())

        args = [
            command,
            *resolve_cli_args(command, self._config.args, self._config.permission_mode),
        ]

        if "--output-format" in args and "stream-json" in args and "--verbose" not in args:
            args.append("--verbose")

        resumed: CliSessionRecord | None = None
        if _supports_resume(command) and "--resume" not in args:
            resumed = await self._sessions.resumable(session_id, cwd)
            if resumed is not None:
                args.extend(["--resume", resumed.cli_session_id])
                logger.info(
                    "cli_resume name=%s session=%s cli_session=%s",
                    self._name,
                    session_id,
                    resumed.cli_session_id,
                )

        if self._config.max_turns > 0 and _supports_max_turns(command):
            args.extend(["--max-turns", str(self._config.max_turns)])

        uses_stdin = any(arg == "-p" for arg in args)
        if not uses_stdin:
            args.append(prompt)

        from myrm_agent_harness.utils.os_compat import get_process_group_kwargs

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE if uses_stdin else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=safe_env,
            cwd=cwd,
            **get_process_group_kwargs(),
        )
        self._alive = True

        if uses_stdin and self._process.stdin is not None:
            self._process.stdin.write(prompt.encode("utf-8"))
            self._process.stdin.write(b"\n")
            await self._process.stdin.drain()
            self._process.stdin.close()
            await self._process.stdin.wait_closed()

        has_text = False
        stderr_chunks: list[bytes] = []

        async def _drain_stderr() -> None:
            if self._process is not None and self._process.stderr is not None:
                stderr_chunks.append(await self._process.stderr.read())

        stderr_task = asyncio.create_task(_drain_stderr())

        if self._process.stdout is not None:
            async for line_bytes in self._process.stdout:
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                self._capture_cli_session_id(line, session_id, cwd)
                event = parse_ndjson_line(line, session_id)
                if event is not None:
                    if event.type == RuntimeEventType.TEXT_DELTA:
                        has_text = True
                    yield event

        await stderr_task
        proc = self._process
        if proc is None:
            self._alive = False
            return
        return_code = await proc.wait()
        self._alive = False

        # A resumed turn the CLI itself fails (positive exit code) without output means it no longer knows
        # the conversation (cleared externally or expired): drop the id so the next turn starts fresh instead
        # of failing on the same stale --resume. A process we killed (cancel, timeout: negative code) says
        # nothing about the conversation. Otherwise the session id the turn reported is kept and persisted.
        if resumed is not None and return_code > 0 and not has_text:
            await self._sessions.forget(session_id)
            logger.warning(
                "cli_resume_invalid name=%s session=%s dropped stale cli_session=%s",
                self._name,
                session_id,
                resumed.cli_session_id,
            )
        elif _supports_resume(command):
            await self._sessions.persist(session_id)

        if return_code != 0:
            stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace").strip()

            if has_text:
                logger.warning(
                    "cli_process_exited_nonzero name=%s code=%d stderr=%s",
                    self._name,
                    return_code,
                    stderr_text[:200],
                )
            else:
                from myrm_agent_harness.toolkits.acp.runtime.cli.spawn_hints import (
                    format_cli_spawn_failure_message,
                )

                message = format_cli_spawn_failure_message(
                    command,
                    return_code=return_code,
                    stderr=stderr_text,
                )
                yield create_event(
                    RuntimeEventType.ERROR,
                    session_id,
                    error=AcpError(
                        code=AcpErrorCode.PROCESS_CRASHED,
                        message=message,
                        retryable=True,
                    ),
                )
                return

        yield create_event(
            RuntimeEventType.DONE,
            session_id,
            stop_reason="end_turn",
        )

    async def _do_cancel(self, session_id: str) -> None:
        if self._process is None or self._process.returncode is not None:
            return
        pid = self._process.pid
        from myrm_agent_harness.utils.os_compat import kill_process_group

        try:
            if pid is not None:
                kill_process_group(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        try:
            await asyncio.wait_for(self._process.wait(), timeout=5.0)
        except TimeoutError:
            try:
                if pid is not None:
                    kill_process_group(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

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

    def _capture_cli_session_id(self, line: str, session_id: str, cwd: str) -> None:
        """Extract and remember the CLI-native session ID from result events.

        Claude CLI emits ``{"type": "result", "session_id": "..."}`` at the
        end of each turn. We capture this so subsequent calls with the same
        ``session_id`` can use ``--resume`` for context continuity. The record is
        persisted once the turn's outcome is known (see ``_do_run_turn``).
        """
        data = parse_json_line(line)
        if data is None:
            return
        if data.get("type") == "result":
            cli_sid = data.get("session_id")
            if isinstance(cli_sid, str) and cli_sid:
                self._sessions.remember(session_id, CliSessionRecord(cli_sid, cwd))
                logger.info(
                    "cli_session_captured name=%s session=%s cli_session=%s",
                    self._name,
                    session_id,
                    cli_sid,
                )


_MAX_TURNS_COMMANDS = frozenset({"claude"})


def _supports_max_turns(command: str) -> bool:
    """Check if a CLI command supports the ``--max-turns`` flag."""
    base = os.path.basename(command)
    return base in _MAX_TURNS_COMMANDS
