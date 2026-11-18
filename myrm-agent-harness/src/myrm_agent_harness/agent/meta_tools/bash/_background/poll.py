"""Read-side views of background bash jobs: entry snapshots and exit waiting.

[INPUT]
- agent.meta_tools.bash._background.types::BackgroundProcessInfo (POS: job snapshot)
- agent.meta_tools.bash._background.termination::refresh_leftovers (POS: live members of a finished job's group)

[OUTPUT]
- snapshot_entry: detached ``BackgroundProcessInfo`` copy of a live registry entry
- wait_for_exit: block until a job leaves ``running`` or the cap passes

[POS]
Read-side helpers for ``bash_process_tool`` / auto-yield / the GUI activity panel.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.bash._background.termination import refresh_leftovers
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    BackgroundProcessInfo,
    compute_waiting_for_input,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.consume import BackgroundRegistryEntry

_WAIT_POLL_INTERVAL_SECONDS = 0.1


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
    snap.last_stdout_tail = list(entry.stdout_buffer)[-20:]
    snap.last_stderr_tail = list(entry.stderr_buffer)[-20:]
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


__all__ = ["snapshot_entry", "wait_for_exit"]
