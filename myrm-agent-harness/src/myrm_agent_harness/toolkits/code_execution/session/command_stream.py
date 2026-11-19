"""Command stream of a persistent shell session: write one wrapped command, read its output to the end marker.

[INPUT]
session.models::SessionExecutionResult, SessionState (POS: Plain session value types)
session.shell_flavor::ShellFlavor (POS: Platform-specific shell command formatting)
session.stream_output_processor::StreamOutputProcessor (POS: Unified tee/SSE output handling; live text scrubbed on whole lines)
session.stream_buffer::ExecutionStreamBuffer (POS: Zero-copy byte stream parsing)
session.value_masker::ValueMasker, printed_forms (POS: Exact-value masking of the credentials delivered to a command, in the forms a client prints them)
utils.runtime.cancel_hook::DeadlineCut, cut_deadline_on_cancel (POS: end a timeout scope as soon as the request token is cancelled)

[OUTPUT]
CommandStreamMixin: ``_execute_core_stream`` for ``PersistentSession``.
CANCELLED_WHILE_RUNNING / CANCELLED_BEFORE_START / CANCELLED_EXIT_CODE: result of a command stopped by its request.

[POS]
Output pump of the persistent shell. A command ends in one of four ways: its end marker, a dead shell, the timeout
or a cancelled request. The last two share one exit: the shell tree is killed, the session is marked TERMINATED so
the next command rebuilds it, and the output produced so far is returned. A dead shell (killed, crashed or closed
under the command) ends its command as a failure that says the command may have run; the command is never
replayed. The credentials delivered to a command (``CommandEnv.scoped``) are masked in everything it prints, before
the output is teed, streamed or returned.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.code_execution.session.models import SessionExecutionResult
from myrm_agent_harness.toolkits.code_execution.session.value_masker import ValueMasker, printed_forms
from myrm_agent_harness.utils.runtime.cancel_hook import DeadlineCut, cut_deadline_on_cancel

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.code_execution.platform import PlatformInfo
    from myrm_agent_harness.toolkits.code_execution.session.models import CommandEnv, SessionConfig
    from myrm_agent_harness.toolkits.code_execution.session.shell_flavor import ShellFlavor
    from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

logger = logging.getLogger(__name__)

CANCELLED_EXIT_CODE = 130
_COMMAND_STOPPED_NOTICE = (
    "The command was terminated and may have been only partially applied; the shell was restarted, "
    "so its working directory and exported variables are reset."
)
CANCELLED_WHILE_RUNNING = f"Cancelled: the run was stopped while this command was running. {_COMMAND_STOPPED_NOTICE}"
CANCELLED_BEFORE_START = "Cancelled: the run was stopped before this command started, so it did not run."
# A command is never replayed on a new shell (it may already have run), so the result tells the agent instead.
_SESSION_DIED_NOTICE = (
    "The command may have been only partially applied; the next command starts a new shell, "
    "so its working directory and exported variables are reset."
)


def _generate_marker(prefix: str) -> str:
    """Return a unique per-command output boundary marker.

    Randomised so user command output can never collide with the marker text.
    A fixed literal (``__MYRM_END__`` etc.) would be matched inside user
    output, silently truncating the captured stdout and misreporting the exit
    code.
    """
    return f"__MYRM_{prefix}_{secrets.token_hex(8)}__"


def _credential_masker(env: CommandEnv | None) -> ValueMasker | None:
    """The masker that hides the credentials delivered to one command from everything it prints."""
    return ValueMasker(printed_forms(env.scoped.values())) if env is not None and env.scoped else None


class CommandStreamMixin:
    """Command I/O of ``PersistentSession``; everything else it needs is declared below for the type checker."""

    if TYPE_CHECKING:
        config: SessionConfig
        process: asyncio.subprocess.Process | None
        _flavor: ShellFlavor
        _platform: PlatformInfo

        async def _discard_shell(self) -> None: ...

    async def _execute_core_stream(
        self,
        cmd_to_run: str,
        original_command: str,
        timeout: int,
        cancel_token: CancellationToken | None = None,
        env: CommandEnv | None = None,
    ) -> SessionExecutionResult:
        # ``close()`` clears ``self.process`` while a command still reads from it, so the pump keeps its own handle:
        # a shell closed under the command then ends it as a dead shell instead of failing on a missing process.
        proc = self.process
        if not proc or not proc.stdin or not proc.stdout:
            return SessionExecutionResult(False, "", "", 1, error="Process unavailable")

        end_marker = _generate_marker("END")
        exit_marker = _generate_marker("EXIT")
        full_cmd = self._flavor.build_wrapped_command(
            cmd_to_run, exit_marker, end_marker, self._platform.exit_code_var, env
        )

        try:
            proc.stdin.write(full_cmd.encode("utf-8", errors="surrogateescape"))
            await proc.stdin.drain()
        except Exception as e:
            logger.error("IPC write failure: %s", e)
            await self._discard_shell()
            return SessionExecutionResult(False, "", "", 1, error="IPC write failure")

        import aiofiles

        from myrm_agent_harness.toolkits.code_execution.session.stream_buffer import (
            ExecutionStreamBuffer,
        )
        from myrm_agent_harness.toolkits.code_execution.session.stream_output_processor import (
            StreamOutputProcessor,
        )
        from myrm_agent_harness.utils.event_utils import dispatch_custom_event

        stream_buf = ExecutionStreamBuffer(masker=_credential_masker(env))
        sop = StreamOutputProcessor()
        tee_file_path = sop.setup_tee(self.config.work_dir)
        cut = DeadlineCut()
        shell_ended = False

        try:
            async with (
                aiofiles.open(tee_file_path, "w", encoding="utf-8") as tee_file,
                asyncio.timeout(timeout) as deadline,
                cut_deadline_on_cancel(cancel_token, deadline, cut),
            ):
                while not stream_buf.done:
                    chunk = await proc.stdout.read(8192)
                    if not chunk:
                        shell_ended = True
                        break

                    safe_text = stream_buf.process_bytes(chunk, exit_marker, end_marker)
                    if safe_text:
                        await sop.write_tee(tee_file, safe_text)
                        sse_emit = sop.accumulate_sse(safe_text)
                        if sse_emit:
                            with contextlib.suppress(RuntimeError):
                                await dispatch_custom_event("tool_stdout_chunk", {"chunk": sse_emit})

                remaining = sop.flush()
                if remaining:
                    from contextlib import suppress

                    with suppress(RuntimeError):
                        await dispatch_custom_event("tool_stdout_chunk", {"chunk": remaining})
        except TimeoutError:
            # A command that never finishes wedges the shell; leaving the
            # process alive poisons every later execute. Kill the tree and
            # mark TERMINATED so the next call transparently rebuilds the
            # session. A request that was cancelled meanwhile takes the same
            # exit, but is no failure of the shell.
            await self._discard_shell()
            if cut.by_cancel:
                return SessionExecutionResult(
                    False,
                    stream_buf.get_final_output(),
                    "",
                    CANCELLED_EXIT_CODE,
                    error=CANCELLED_WHILE_RUNNING,
                )
            return SessionExecutionResult(
                False,
                stream_buf.get_final_output(),
                f"Timeout after {timeout}s. {_COMMAND_STOPPED_NOTICE}",
                124,
                error="Timeout",
            )
        except asyncio.CancelledError:
            # The task running the command was cancelled from outside (tool deadline, shutdown): the command
            # must not outlive it, or it keeps running unseen and blocks the shell for the next command.
            await self._discard_shell()
            raise

        if shell_ended:
            # The shell died under the command (killed, crashed, ran out of memory, closed). The next command starts
            # a new shell; this one is not replayed, because it may already have run. A shell that has closed its
            # output but is not reaped yet has no exit status to report.
            await self._discard_shell()
            rc = proc.returncode
            status = f" (rc={rc})" if rc is not None else ""
            err = f"Session process ended unexpectedly{status}. {_SESSION_DIED_NOTICE}"
            return SessionExecutionResult(
                False,
                stream_buf.get_final_output(),
                err,
                rc if rc is not None else 1,
                error=err,
            )

        if stream_buf.parse_failed:
            # The text between the two markers is not an exit code: the marker
            # lines were consumed or rewritten instead of printed (a command read
            # them from the session's stdin, which the bash block shields and the
            # Windows flavors do not, or changed how the shell prints). The
            # boundary can no longer be trusted, which is indistinguishable from
            # a permanently broken shell.
            await self._discard_shell()
            return SessionExecutionResult(
                False,
                "",
                "Session output boundary corrupted",
                1,
                error="Session corrupted",
            )

        # The note follows a cut output only; the buffer keeps room for it so stdout still fits the output cap.
        truncation_note = sop.build_truncation_system_note()
        stdout = stream_buf.get_final_output(reserve=len(truncation_note)).rstrip("\n")
        exit_code = stream_buf.exit_code

        if stream_buf.truncated or sop.tee_truncated:
            stdout += truncation_note

        if exit_code == 0:
            success = True
        else:
            from myrm_agent_harness.toolkits.code_execution.executors.common.exit_classify import (
                classify_exit_code,
            )

            success = classify_exit_code(original_command, exit_code, stdout)

        return SessionExecutionResult(success, stdout, "", exit_code)
