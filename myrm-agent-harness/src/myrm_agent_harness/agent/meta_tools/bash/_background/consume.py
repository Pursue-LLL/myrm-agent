"""Stdout/stderr reader loop for a single background bash registry entry.

[INPUT]
- agent.meta_tools.bash._background.line_assembler::LineAssembler (POS: byte chunks to whole lines plus the unfinished last line)
- agent.meta_tools.bash._background.output_spill::BackgroundOutputSpillWriter (POS: full-output half of the output chain: the job's log, every line as printed, at the foreground evicted-file location)
- agent.meta_tools.bash._background.types::BackgroundProcessInfo (POS: job snapshot)
- agent.meta_tools.bash._background.termination::GroupMember / leader_id_reassigned / snapshot_group_members (POS: identity of the processes a job's group still holds, and whether the leader's pid still belongs to the job)
- agent.security.redact::redact_sensitive_text (POS: facade of the redaction domain; masks a progress message)
- toolkits.code_execution.executors.models::AsyncProcessProtocol (POS: async process handle)

[OUTPUT]
- BackgroundRegistryEntry: Live registry row with ring buffers, the unfinished last line of each stream, log writer, the leader's recorded identity and the processes the job left running
- UnfinishedTail: What a stream printed after its last newline, with the time it last changed
- consume_background_entry: Read pipes in blocks until exit (whole lines go to the log and the ring as printed and through progress parsing; the unfinished line stays visible), record what the job left running, persist terminal state, close the log, invoke finish hook

[POS]
I/O consumer for BackgroundProcessRegistry — keeps registry orchestration separate from pipe reading.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from collections import deque
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

from myrm_agent_harness.agent.meta_tools.bash._background.line_assembler import LineAssembler
from myrm_agent_harness.agent.meta_tools.bash._background.termination import (
    leader_id_reassigned,
    snapshot_group_members,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    BackgroundProcessInfo,
    FinishListener,
    ProgressListener,
)
from myrm_agent_harness.agent.security.redact import redact_sensitive_text

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.output_spill import (
        BackgroundOutputSpillWriter,
    )
    from myrm_agent_harness.agent.meta_tools.bash._background.termination import GroupMember
    from myrm_agent_harness.toolkits.code_execution.executors.models import (
        AsyncProcessProtocol,
    )

logger = logging.getLogger(__name__)

# One recorded line keeps its first 32 Ki characters; the rest is counted in a marker.
_LINE_MAX_CHARS = 32 * 1024
# Bytes asked of a pipe per read: a prompt or a progress bar shows up as soon as the program prints it.
_READ_CHUNK_BYTES = 64 * 1024
# Minimum interval between asynchronous progress listener dispatches (10Hz).
# Aligns with builtin_notify.py's 10 req/s rate-limiting, preventing event storms
# and cascading frontend HTTP refresh requests on high-frequency log bursts.
_PROGRESS_EMIT_INTERVAL_S = 0.1

StreamName = Literal["stdout", "stderr"]


class UnfinishedTail(NamedTuple):
    """What a stream printed after its last newline, and when it last changed."""

    at: float
    text: str


_NO_TAIL = UnfinishedTail(0.0, "")


@dataclass
class BackgroundRegistryEntry:
    """Internal registry record (carries the live process handle).

    ``stdout_buffer`` and ``stderr_buffer`` are the ring tails of the two streams, newest line last.
    ``stdout_total`` and ``stderr_total`` count every line a stream produced, so a total above the ring's
    length means older lines fell off (``output_dropped``).

    ``stdout_unfinished`` and ``stderr_unfinished`` hold what each stream printed after its last newline (a prompt
    waits here until it is answered). They are fixed slots that the reader task replaces as a whole and other
    threads read, so no reader ever sees a half-written value.

    ``leader`` is the job leader as it was at registration; it tells a later
    signal whether the leader's pid still belongs to this job.
    ``leftover_members`` are the processes the job's group still held when its
    leader exited (daemons the job detached, children that kept the pipes
    open); they are what a later stop has to reach.
    """

    info: BackgroundProcessInfo
    proc: AsyncProcessProtocol
    stdout_buffer: deque[str]
    stderr_buffer: deque[str]
    reader_task: asyncio.Task[None] | None = None
    finish_listener: FinishListener | None = None
    progress_listener: ProgressListener | None = None
    spill_writer: BackgroundOutputSpillWriter | None = None
    stdout_total: int = 0
    stderr_total: int = 0
    stdout_unfinished: UnfinishedTail = _NO_TAIL
    stderr_unfinished: UnfinishedTail = _NO_TAIL
    stdin_lock: asyncio.Lock | None = None
    stdin_closed: bool = False
    last_progress_emit_at: float = 0.0
    leader: GroupMember | None = None
    leftover_members: tuple[GroupMember, ...] = ()

    def append_line(self, stream: StreamName, text: str) -> None:
        """Add one line to a stream's ring and count it."""
        if stream == "stderr":
            self.stderr_buffer.append(text)
            self.stderr_total += 1
        else:
            self.stdout_buffer.append(text)
            self.stdout_total += 1

    def set_unfinished(self, stream: StreamName, at: float, text: str) -> None:
        """Replace what a stream printed after its last newline (empty ``text`` once a newline ended it)."""
        tail = UnfinishedTail(at, text)
        if stream == "stderr":
            self.stderr_unfinished = tail
        else:
            self.stdout_unfinished = tail

    @property
    def output_dropped(self) -> bool:
        """True once a stream produced more lines than its ring holds, so ``output`` cannot return the oldest."""
        return self.stdout_total > len(self.stdout_buffer) or self.stderr_total > len(self.stderr_buffer)


async def consume_background_entry(
    entry: BackgroundRegistryEntry,
    *,
    snapshot: Callable[[BackgroundRegistryEntry], BackgroundProcessInfo],
    schedule_reap: Callable[[int], None],
    clear_session_if_idle: Callable[[str | None], None],
) -> None:
    """Read stdout/stderr until the child exits; persist state and notify listeners."""
    from myrm_agent_harness.agent.meta_tools.bash._background.progress import (
        try_parse_progress_line,
    )

    async def _emit_progress(progress: dict[str, object], *, force: bool = False) -> None:
        now = time.time()
        entry.info.last_progress = {**progress, "updated_at": now}
        listener = entry.progress_listener
        if listener is None:
            return

        # Adaptive throttle: 100% completion or explicit checkpoint categories
        # bypass the interval check so final state and milestones arrive with zero latency.
        is_terminal_progress = progress.get("progress") == 100
        has_checkpoint_category = bool(progress.get("category"))
        if (
            not (force or is_terminal_progress or has_checkpoint_category)
            and (now - entry.last_progress_emit_at) < _PROGRESS_EMIT_INTERVAL_S
        ):
            return

        entry.last_progress_emit_at = now
        try:
            await listener(entry.info, progress)
        except Exception as exc:  # pragma: no cover — best-effort
            logger.debug(
                "background progress listener for pid=%s failed: %s",
                entry.info.pid,
                exc,
            )

    async def _record_line(line: str, stream_name: StreamName) -> None:
        """A complete line goes to the log and the ring as the program printed it; a read masks the secrets in it."""
        spill = entry.spill_writer
        if spill is not None:
            spill.append_line(stream_name, line)
            if spill.vault_log_ref and entry.info.vault_log_ref != spill.vault_log_ref:
                entry.info.vault_log_ref = spill.vault_log_ref
                from myrm_agent_harness.agent.meta_tools.bash._background.store_sync import (
                    persist_vault_log_ref,
                )

                persist_vault_log_ref(entry.info)
        entry.append_line(stream_name, line)
        progress = try_parse_progress_line(line)
        if progress is not None:
            # A progress message is shown outside the output reads, so it comes from the masked line: a message cut from
            # the raw line could keep the start of a secret.
            progress = try_parse_progress_line(redact_sensitive_text(line))
        if progress is not None:
            await _emit_progress(progress)

    async def _pipe(stream: object, stream_name: StreamName) -> None:
        read = getattr(stream, "read", None)
        if read is None:
            return
        assembler = LineAssembler(max_line_chars=_LINE_MAX_CHARS)
        while True:
            try:
                chunk = await read(_READ_CHUNK_BYTES)
            except (ConnectionError, OSError, asyncio.CancelledError):
                return
            if not chunk:
                break
            # Any byte is output: a progress bar that redraws one line with carriage returns never completes a line.
            entry.info.last_output_at = time.time()
            for line in assembler.feed(chunk):
                await _record_line(line, stream_name)
            entry.set_unfinished(stream_name, entry.info.last_output_at, assembler.tail)
        for line in assembler.finish():
            await _record_line(line, stream_name)
        entry.set_unfinished(stream_name, 0.0, "")

    try:
        await asyncio.gather(
            _pipe(entry.proc.stdout, "stdout"),
            _pipe(entry.proc.stderr, "stderr"),
            return_exceptions=True,
        )
        exit_code = await entry.proc.wait()
        # A leader pid that another process holds now names that process's group, not the job's.
        entry.leftover_members = () if leader_id_reassigned(entry.leader) else snapshot_group_members(entry.info.pid)
        entry.info.exit_code = exit_code
        if entry.info.status == "running":
            entry.info.status = "exited"
        from myrm_agent_harness.agent.meta_tools.bash._tool.background_listeners import (
            classify_background_exit,
        )

        entry.info.error_category = classify_background_exit(entry.info)
        from myrm_agent_harness.agent.meta_tools.bash._background.store_sync import (
            persist_terminal_state,
        )

        persist_terminal_state(entry.info)
    except asyncio.CancelledError:
        return
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("background reader for pid=%s crashed: %s", entry.info.pid, exc)
    finally:
        # A coroutine closed unfinished (an abandoned task collected by the garbage collector) has no loop left to
        # await on, and the registry lock may be held by the very thread that triggered the collection: finishing
        # would wait on it forever.
        if isinstance(sys.exc_info()[1], GeneratorExit):
            raise
        # The log is complete before anything is told the job is over; whatever the log does, the job still settles.
        if entry.spill_writer is not None:
            with suppress(Exception):
                entry.spill_writer.close()
        # Trailing flush: deliver un-emitted tail progress trapped by the 10Hz throttle before finish.
        tail_progress = entry.info.last_progress
        tail_updated_at = tail_progress.get("updated_at") if tail_progress is not None else None
        if (
            tail_progress is not None
            and isinstance(tail_updated_at, int | float)
            and entry.last_progress_emit_at < tail_updated_at
        ):
            with suppress(Exception):
                await _emit_progress(tail_progress, force=True)

        listener = entry.finish_listener
        if listener is not None:
            try:
                await listener(snapshot(entry))
            except Exception as exc:  # pragma: no cover — best-effort
                logger.debug(
                    "background finish listener for pid=%s failed: %s",
                    entry.info.pid,
                    exc,
                )
        clear_session_if_idle(entry.info.session_id)
        schedule_reap(entry.info.pid)


__all__ = ["BackgroundRegistryEntry", "UnfinishedTail", "consume_background_entry"]
