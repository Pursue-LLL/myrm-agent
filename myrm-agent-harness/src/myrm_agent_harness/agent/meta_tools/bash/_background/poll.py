"""Read-side views of background bash jobs: poll payloads, entry snapshots, exit waiting.

[INPUT]
- collections.deque ring buffers of (cursor, text) pairs
- agent.meta_tools.bash._background.types::BackgroundProcessInfo (POS: job snapshot)
- agent.meta_tools.bash._background.termination::refresh_leftovers (POS: live members of a finished job's group)

[OUTPUT]
- build_poll_output: stdout/stderr slices + next_cursor + poll_hint
- snapshot_entry: detached ``BackgroundProcessInfo`` copy of a live registry entry
- wait_for_exit: block until a job leaves ``running`` or the cap passes

[POS]
Read-side helpers for ``bash_process_tool`` / auto-yield / the GUI activity panel.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.bash._background.termination import refresh_leftovers
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    BackgroundProcessInfo,
    compute_waiting_for_input,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.consume import BackgroundRegistryEntry

_OUTPUT_TAIL_LINES = 200
_WAIT_POLL_INTERVAL_SECONDS = 0.1
_POLL_BACKOFF_MS: tuple[int, ...] = (5000, 10000, 20000, 30000, 60000)


def build_poll_output(
    *,
    stdout_buffer: deque[tuple[int, str]],
    stderr_buffer: deque[tuple[int, str]],
    cursor: int,
    empty_poll_streak: int,
    max_lines: int,
    since_cursor: int | None,
) -> tuple[dict[str, object], int]:
    """Return poll payload and updated empty_poll_streak."""
    baseline = since_cursor if since_cursor is not None else 0
    stdout_items = [(cur, text) for cur, text in stdout_buffer if cur > baseline]
    stderr_items = [(cur, text) for cur, text in stderr_buffer if cur > baseline]
    has_new_output = bool(stdout_items or stderr_items)
    streak = empty_poll_streak
    if since_cursor is not None:
        streak = 0 if has_new_output else empty_poll_streak + 1
    streak_idx = min(streak, len(_POLL_BACKOFF_MS) - 1)
    poll_hint = {
        "has_new_output": has_new_output,
        "suggested_wait_ms": _POLL_BACKOFF_MS[streak_idx],
    }

    if since_cursor is not None and (stdout_buffer or stderr_buffer):
        oldest_kept = min(
            stdout_buffer[0][0] if stdout_buffer else cursor,
            stderr_buffer[0][0] if stderr_buffer else cursor,
        )
        dropped = oldest_kept > baseline + 1 and (
            len(stdout_buffer) == _OUTPUT_TAIL_LINES or len(stderr_buffer) == _OUTPUT_TAIL_LINES
        )
    else:
        dropped = False

    if since_cursor is not None:
        # Incremental streaming mode: slice forward [:max_lines] and advance next_cursor
        # to the maximum cursor actually consumed in this batch, preventing log gaps.
        stdout_slice = stdout_items[:max_lines]
        stderr_slice = stderr_items[:max_lines]
        consumed_cursors = [cur for cur, _ in stdout_slice] + [cur for cur, _ in stderr_slice]
        next_cursor = max(consumed_cursors) if consumed_cursors else baseline
        stdout_output = [text for _, text in stdout_slice]
        stderr_output = [text for _, text in stderr_slice]
    else:
        # Snapshot mode: return the latest tail lines and global latest cursor.
        next_cursor = cursor
        stdout_output = [text for _, text in stdout_items[-max_lines:]]
        stderr_output = [text for _, text in stderr_items[-max_lines:]]

    payload: dict[str, object] = {
        "stdout": stdout_output,
        "stderr": stderr_output,
        "next_cursor": next_cursor,
        "dropped": dropped,
        "poll_hint": poll_hint,
    }
    return payload, streak


def snapshot_entry(entry: BackgroundRegistryEntry) -> BackgroundProcessInfo:
    """Detached copy of a live entry, safe to serialise while the registry keeps mutating the original.

    ``leftover_processes`` is read from the live process group, which also refreshes what the entry remembers of it.
    """
    info = entry.info
    snap = BackgroundProcessInfo(
        job_id=info.job_id,
        pid=info.pid,
        command=info.command,
        session_id=info.session_id,
        started_at=info.started_at,
        status=info.status,
        exit_code=info.exit_code,
        error_category=info.error_category,
        vault_log_ref=info.vault_log_ref,
        last_output_at=info.last_output_at or info.started_at,
        leftover_processes=len(refresh_leftovers(entry)),
    )
    snap.last_stdout_tail = [text for _, text in list(entry.stdout_buffer)[-20:]]
    snap.last_stderr_tail = [text for _, text in list(entry.stderr_buffer)[-20:]]
    # Defensive shallow copy: callers serialise this dict into JSON; any
    # in-place mutation by the consumer must not bleed back into the
    # live registry record (parsers append/normalise fields downstream).
    snap.last_progress = dict(info.last_progress) if info.last_progress else None
    stdin_obj = getattr(entry.proc, "stdin", None)
    stdin_available = stdin_obj is not None and not entry.stdin_closed
    snap.stdin_closed = entry.stdin_closed
    snap.waiting_for_input = compute_waiting_for_input(
        status=snap.status,
        last_output_at=snap.last_output_at,
        started_at=snap.started_at,
        stdin_closed=entry.stdin_closed,
        stdin_available=stdin_available,
    )
    return snap


async def wait_for_exit(
    get_info: Callable[[int], BackgroundProcessInfo | None],
    pid: int,
    *,
    timeout_seconds: float,
    max_seconds: float,
) -> dict[str, object]:
    """Wait until job ``pid`` is no longer running or ``timeout_seconds`` (capped at ``max_seconds``) elapses."""
    capped = min(max(timeout_seconds, 0.0), max_seconds)
    deadline = time.monotonic() + capped
    while time.monotonic() < deadline:
        info = get_info(pid)
        if info is None:
            return {"found": False, "still_running": False, "pid": pid}
        if info.status != "running":
            return {
                "found": True,
                "still_running": False,
                "pid": pid,
                "status": info.status,
                "exit_code": info.exit_code,
                "error_category": info.error_category,
            }
        await asyncio.sleep(_WAIT_POLL_INTERVAL_SECONDS)
    info = get_info(pid)
    if info is None:
        return {"found": False, "still_running": False, "pid": pid}
    return {
        "found": True,
        "still_running": info.status == "running",
        "pid": pid,
        "status": info.status,
        "exit_code": info.exit_code,
        "error_category": info.error_category,
    }


__all__ = ["build_poll_output", "snapshot_entry", "wait_for_exit"]
