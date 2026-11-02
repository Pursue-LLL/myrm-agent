"""Stdout/stderr reader loop for a single background bash registry entry.

[INPUT]
- agent.meta_tools.bash._background.types::BackgroundProcessInfo (POS: job snapshot)
- agent.meta_tools.bash._background.termination::GroupMember / leader_id_reassigned / snapshot_group_members (POS: identity of the processes a job's group still holds, and whether the leader's pid still belongs to the job)
- toolkits.code_execution.executors.models::AsyncProcessProtocol (POS: async process handle)

[OUTPUT]
- BackgroundRegistryEntry: Live registry row with ring buffers, spill writer, the leader's recorded identity and the processes the job left running
- consume_background_entry: Read pipes until exit, record what the job left running, persist terminal state, invoke finish hook

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
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.bash._background.termination import (
    leader_id_reassigned,
    snapshot_group_members,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    BackgroundProcessInfo,
    FinishListener,
    ProgressListener,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.output_spill import (
        BackgroundOutputSpillWriter,
    )
    from myrm_agent_harness.agent.meta_tools.bash._background.termination import GroupMember
    from myrm_agent_harness.toolkits.code_execution.executors.models import (
        AsyncProcessProtocol,
    )

logger = logging.getLogger(__name__)

_LINE_MAX_BYTES = 32 * 1024
# Minimum interval between asynchronous progress listener dispatches (10Hz).
# Aligns with builtin_notify.py's 10 req/s rate-limiting, preventing event storms
# and cascading frontend HTTP refresh requests on high-frequency log bursts.
_PROGRESS_EMIT_INTERVAL_S = 0.1


@dataclass
class BackgroundRegistryEntry:
    """Internal registry record (carries the live process handle).

    Each buffered line is stored as ``(cursor, text)``. ``cursor`` is a
    process-wide monotonically increasing integer shared between stdout and
    stderr; this lets ``get_output(since_cursor=...)`` filter both streams
    against the same cursor without confusing rates (a busy stderr will not
    eat into stdout's quota or vice versa).

    ``leader`` is the job leader as it was at registration; it tells a later
    signal whether the leader's pid still belongs to this job.
    ``leftover_members`` are the processes the job's group still held when its
    leader exited (daemons the job detached, children that kept the pipes
    open); they are what a later stop has to reach.
    """

    info: BackgroundProcessInfo
    proc: AsyncProcessProtocol
    stdout_buffer: deque[tuple[int, str]]
    stderr_buffer: deque[tuple[int, str]]
    reader_task: asyncio.Task[None] | None = None
    finish_listener: FinishListener | None = None
    progress_listener: ProgressListener | None = None
    spill_writer: BackgroundOutputSpillWriter | None = None
    cursor: int = 0
    empty_poll_streak: int = 0
    stdin_lock: asyncio.Lock | None = None
    stdin_closed: bool = False
    last_progress_emit_at: float = 0.0
    leader: GroupMember | None = None
    leftover_members: tuple[GroupMember, ...] = ()


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

    async def _pipe(stream: object, sink: deque[tuple[int, str]]) -> None:
        reader = getattr(stream, "readline", None)
        if reader is None:
            return
        while True:
            try:
                chunk = await reader()
            except asyncio.LimitOverrunError as exc:
                drain_method = getattr(stream, "readexactly", None)
                if drain_method is not None:
                    with suppress(asyncio.IncompleteReadError, ConnectionError, OSError):
                        await drain_method(exc.consumed)
                entry.cursor += 1
                sink.append((entry.cursor, f"[output line >{exc.consumed} bytes truncated]"))
                continue
            except (ConnectionError, OSError, asyncio.CancelledError):
                return
            if not chunk:
                break
            raw = (chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)).rstrip()
            if len(raw) > _LINE_MAX_BYTES:
                text = raw[:_LINE_MAX_BYTES] + f"... [+{len(raw) - _LINE_MAX_BYTES} bytes truncated]"
            else:
                text = raw
            from myrm_agent_harness.agent.security.redact import redact_sensitive_text

            text = redact_sensitive_text(text)
            spill = entry.spill_writer
            if spill is not None:
                stream_name = "stderr" if sink is entry.stderr_buffer else "stdout"
                spill.append_line(stream_name, text)
                if spill.vault_log_ref and entry.info.vault_log_ref != spill.vault_log_ref:
                    entry.info.vault_log_ref = spill.vault_log_ref
                    from myrm_agent_harness.agent.meta_tools.bash._background.store_sync import (
                        persist_vault_log_ref,
                    )

                    persist_vault_log_ref(entry.info)
            entry.cursor += 1
            sink.append((entry.cursor, text))
            entry.info.last_output_at = time.time()
            progress = try_parse_progress_line(text)
            if progress is not None:
                await _emit_progress(progress)

    try:
        await asyncio.gather(
            _pipe(entry.proc.stdout, entry.stdout_buffer),
            _pipe(entry.proc.stderr, entry.stderr_buffer),
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


__all__ = ["BackgroundRegistryEntry", "consume_background_entry"]
