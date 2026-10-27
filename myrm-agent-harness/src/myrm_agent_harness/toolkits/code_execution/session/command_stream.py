"""Command stream of a persistent shell session: write one wrapped command, read its output to the end marker.

[INPUT]
session.models::SessionExecutionResult, SessionState (POS: Plain session value types)
session.shell_flavor::ShellFlavor (POS: Platform-specific shell command formatting)
session.stream_output_processor::StreamOutputProcessor (POS: Unified tee/SSE output handling)
session.stream_buffer::ExecutionStreamBuffer (POS: Zero-copy byte stream parsing)
executors.models::scrub_sensitive_info (POS: PII scrubbing for output streams)
security.script_armor::prepare_armored_command (POS: Execution security armor wrapping script materialization)
utils.runtime.cancel_hook::DeadlineCut, cut_deadline_on_cancel (POS: end a timeout scope as soon as the request token is cancelled)

[OUTPUT]
CommandStreamMixin: ``_execute_core_stream`` / ``execute_stream`` for ``PersistentSession``.
CANCELLED_WHILE_RUNNING / CANCELLED_BEFORE_START / CANCELLED_EXIT_CODE: result of a command stopped by its request.

[POS]
Output pump of the persistent shell. A command ends in one of four ways: its end marker, a dead shell, the timeout
or a cancelled request. The last two share one exit: the shell tree is killed, the session is marked TERMINATED so
the next command rebuilds it, and the output produced so far is returned.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.code_execution.security.script_armor import prepare_armored_command
from myrm_agent_harness.toolkits.code_execution.session.models import SessionExecutionResult
from myrm_agent_harness.utils.runtime.cancel_hook import DeadlineCut, cut_deadline_on_cancel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.platform import PlatformInfo
    from myrm_agent_harness.toolkits.code_execution.session.models import SessionConfig
    from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import ShellFlavor
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)

CANCELLED_EXIT_CODE = 130
CANCELLED_WHILE_RUNNING = (
    "Cancelled: the run was stopped while this command was running. The command was terminated and may have been "
    "only partially applied; the shell was restarted, so its working directory and exported variables are reset."
)
CANCELLED_BEFORE_START = "Cancelled: the run was stopped before this command started, so it did not run."


def _generate_marker(prefix: str) -> str:
    """Return a unique per-command output boundary marker.

    Randomised so user command output can never collide with the marker text.
    A fixed literal (``__MYRM_END__`` etc.) would be matched inside user
    output, silently truncating the captured stdout and misreporting the exit
    code.
    """
    return f"__MYRM_{prefix}_{secrets.token_hex(8)}__"


class CommandStreamMixin:
    """Command I/O of ``PersistentSession``; everything else it needs is declared below for the type checker."""

    if TYPE_CHECKING:
        config: SessionConfig
        process: asyncio.subprocess.Process | None
        _lock: asyncio.Lock
        _flavor: ShellFlavor
        _platform: PlatformInfo
        _consecutive_failures: int
        _last_returncode: int | None
        _SESSION_DIED_SENTINEL: str

        async def _ensure_active(self) -> None: ...
        async def _precheck_bash_syntax(self, command: str) -> str | None: ...
        async def _discard_shell(self) -> None: ...

    async def _execute_core_stream(
        self,
        cmd_to_run: str,
        original_command: str,
        timeout: int,
        is_armored: bool = False,
        cancel_token: CancellationToken | None = None,
    ) -> SessionExecutionResult:
        if not self.process or not self.process.stdin or not self.process.stdout:
            return SessionExecutionResult(False, "", "", 1, error="Process unavailable", is_armored=is_armored)

        end_marker = _generate_marker("END")
        exit_marker = _generate_marker("EXIT")
        full_cmd = self._flavor.build_wrapped_command(cmd_to_run, exit_marker, end_marker, self._platform.exit_code_var)

        try:
            self.process.stdin.write(full_cmd.encode("utf-8", errors="surrogateescape"))
            await self.process.stdin.drain()
        except Exception as e:
            logger.error("IPC write failure: %s", e)
            self._consecutive_failures += 1
            return SessionExecutionResult(False, "", "", 1, error="IPC write failure", is_armored=is_armored)

        import aiofiles

        from myrm_agent_harness.toolkits.code_execution.executors.models import (
            scrub_sensitive_info,
        )
        from myrm_agent_harness.toolkits.code_execution.session.stream_buffer import (
            ExecutionStreamBuffer,
        )
        from myrm_agent_harness.toolkits.code_execution.session.stream_output_processor import (
            StreamOutputProcessor,
        )
        from myrm_agent_harness.utils.event_utils import dispatch_custom_event

        stream_buf = ExecutionStreamBuffer()
        sop = StreamOutputProcessor()
        tee_file_path = sop.setup_tee(self.config.work_dir)
        cut = DeadlineCut()

        try:
            async with (
                aiofiles.open(tee_file_path, "w", encoding="utf-8") as tee_file,
                asyncio.timeout(timeout) as deadline,
                cut_deadline_on_cancel(cancel_token, deadline, cut),
            ):
                while not stream_buf.done:
                    chunk = await self.process.stdout.read(8192)
                    if not chunk:
                        rc = self.process.returncode
                        self._last_returncode = rc
                        self._consecutive_failures += 1
                        err = f"{self._SESSION_DIED_SENTINEL} (rc={rc})"
                        return SessionExecutionResult(
                            False,
                            stream_buf.get_final_output(),
                            err,
                            rc if rc is not None else 1,
                            error=err,
                        )

                    safe_text = stream_buf.process_bytes(chunk, exit_marker, end_marker)
                    if safe_text:
                        await sop.write_tee(tee_file, safe_text)
                        scrubbed_text = scrub_sensitive_info(safe_text)
                        sse_emit = sop.accumulate_sse(scrubbed_text)
                        if sse_emit:
                            with contextlib.suppress(RuntimeError):
                                await dispatch_custom_event("tool_stdout_chunk", {"chunk": sse_emit})

                remaining = sop.flush()
                if remaining:
                    from contextlib import suppress

                    with suppress(RuntimeError):
                        await dispatch_custom_event("tool_stdout_chunk", {"chunk": remaining})
        except TimeoutError:
            # A wedged shell (blocking command like `cat`/`tail -f`/`sleep 9999`)
            # never finishes; leaving the process alive poisons every later
            # execute. Kill the tree and mark TERMINATED so the next call
            # transparently rebuilds the session. A request that was cancelled
            # meanwhile takes the same exit, but is no failure of the shell.
            await self._discard_shell()
            if cut.by_cancel:
                return SessionExecutionResult(
                    False,
                    stream_buf.get_final_output(),
                    "",
                    CANCELLED_EXIT_CODE,
                    error=CANCELLED_WHILE_RUNNING,
                    is_armored=is_armored,
                )
            self._consecutive_failures += 1
            return SessionExecutionResult(
                False,
                stream_buf.get_final_output(),
                f"Timeout after {timeout}s",
                124,
                error="Timeout",
                is_armored=is_armored,
            )
        except asyncio.CancelledError:
            # The task running the command was cancelled from outside (tool deadline, shutdown): the command
            # must not outlive it, or it keeps running unseen and blocks the shell for the next command.
            await self._discard_shell()
            raise

        if stream_buf.parse_failed:
            # exit_marker was echoed back as raw text (e.g. `cat`/`ssh`/`python
            # -c input()` consumed the trailing marker commands from stdin),
            # which is indistinguishable from a permanently broken shell.
            self._consecutive_failures += 1
            await self._discard_shell()
            return SessionExecutionResult(
                False,
                "",
                "Session output boundary corrupted",
                1,
                error="Session corrupted",
                is_armored=is_armored,
            )

        stdout = stream_buf.get_final_output().rstrip("\n")
        exit_code = stream_buf.exit_code

        if getattr(stream_buf, "_is_truncated", False) or sop.tee_truncated:
            stdout += sop.build_truncation_system_note()

        if exit_code == 0:
            success = True
        else:
            from myrm_agent_harness.toolkits.code_execution.executors.common.exit_classify import (
                classify_exit_code,
            )

            success = classify_exit_code(original_command, exit_code, stdout)

        return SessionExecutionResult(success, stdout, "", exit_code, is_armored=is_armored)

    async def execute_stream(
        self,
        command: str,
        timeout: int | None = None,
        cancel_token: CancellationToken | None = None,
    ) -> AsyncIterator[str]:
        """Yield performance-optimized output stream."""
        timeout = timeout or self.config.timeout
        if cancel_token is not None and cancel_token.is_cancelled:
            yield f"\n[ERROR] {CANCELLED_BEFORE_START}\n"
            return
        await self._ensure_active()

        syntax_error = await self._precheck_bash_syntax(command)
        if syntax_error:
            yield f"\n[ERROR] {syntax_error}\n"
            return

        with prepare_armored_command(
            command,
            work_dir=self.config.work_dir,
            is_windows=self._platform.is_windows,
        ) as cmd_to_run:
            async with self._lock:
                process = self.process
                if process is None or process.stdin is None or process.stdout is None:
                    yield "\n[ERROR] Process unavailable\n"
                    return

                end_marker = _generate_marker("END")
                exit_marker = _generate_marker("EXIT")
                full_cmd = self._flavor.build_wrapped_command(
                    cmd_to_run, exit_marker, end_marker, self._platform.exit_code_var
                )

                process.stdin.write(full_cmd.encode())
                await process.stdin.drain()

                import aiofiles

                from myrm_agent_harness.toolkits.code_execution.executors.models import (
                    scrub_sensitive_info,
                )
                from myrm_agent_harness.toolkits.code_execution.session.stream_buffer import (
                    ExecutionStreamBuffer,
                )
                from myrm_agent_harness.toolkits.code_execution.session.stream_output_processor import (
                    StreamOutputProcessor,
                )

                stream_buf = ExecutionStreamBuffer()
                sop = StreamOutputProcessor()
                tee_file_path = sop.setup_tee(self.config.work_dir)
                cut = DeadlineCut()

                try:
                    async with (
                        aiofiles.open(tee_file_path, "w", encoding="utf-8") as tee_file,
                        asyncio.timeout(timeout) as deadline,
                        cut_deadline_on_cancel(cancel_token, deadline, cut),
                    ):
                        while not stream_buf.done:
                            chunk = await process.stdout.read(4096)
                            if not chunk:
                                yield f"\n[ERROR] {self._SESSION_DIED_SENTINEL}\n"
                                return
                            safe_text = stream_buf.process_bytes(chunk, exit_marker, end_marker)
                            if safe_text:
                                await sop.write_tee(tee_file, safe_text)
                                # Mirror the execute path: scrub before the SSE
                                # valve so real-time UI output never leaks host
                                # paths or credential tokens (tee keeps the raw
                                # log for debugging).
                                sse_emit = sop.accumulate_sse(scrub_sensitive_info(safe_text))
                                if sse_emit:
                                    yield sse_emit

                        remaining = sop.flush()
                        if remaining:
                            yield remaining

                        if stream_buf.parse_failed:
                            await self._discard_shell()
                            yield "\n[ERROR] Session output boundary corrupted\n"
                            return
                except TimeoutError:
                    # Mirror execute(): kill the wedged shell so the next stream
                    # transparently rebuilds instead of re-hanging forever.
                    await self._discard_shell()
                    yield (
                        f"\n[ERROR] {CANCELLED_WHILE_RUNNING}\n"
                        if cut.by_cancel
                        else f"\n[ERROR] Timeout After {timeout}s\n"
                    )
                except asyncio.CancelledError:
                    await self._discard_shell()
                    raise
