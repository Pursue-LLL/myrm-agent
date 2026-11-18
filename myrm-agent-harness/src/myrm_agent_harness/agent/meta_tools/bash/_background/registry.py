"""In-process registry tracking background bash processes started by the agent.

When ``bash_code_execute_tool`` is invoked with ``run_in_background=True`` the
underlying ``LocalExecutor.spawn_background_process`` returns an
``AsyncProcessProtocol`` handle; this registry keeps that handle alive,
buffers stdout/stderr ring-tail for later inspection, and exposes a tiny CRUD
surface used by ``bash_process_tool``.

Lifetime is the agent process lifetime — on a normal exit the :mod:`atexit`
sweep kills every job group, including what a finished job left running, except
a group whose leader pid another process now holds. Each
``session_id`` has its own bucket so parallel chats cannot peek at each other's
background tasks.

The public data types (``BackgroundProcessInfo``, ``BackgroundQuotaError``,
``FinishListener`` / ``ProgressListener``) live in
:mod:`._background.types` so the registry implementation can focus on
runtime behaviour (process I/O, parsing) without a large type
block, and so downstream consumers can import the snapshot without
dragging in the singleton's ``atexit`` hook. Stopping, reaping and the
``atexit`` sweep live in :mod:`._background.lifecycle`.

[INPUT]
- toolkits.code_execution.executors.models::AsyncProcessProtocol (POS: AsyncProcessProtocol — wait/terminate/kill handle.)
- agent.meta_tools.bash._background.types::BackgroundProcessInfo / BackgroundQuotaError / FinishListener / OutputTail / ProgressListener (POS: shared dataclasses & typing.)
- agent.meta_tools.bash._background.lifecycle::RegistryLifecycleMixin (POS: kill / reap / shutdown half of the registry.)
- agent.meta_tools.bash._background.poll::snapshot_entry / unfinished_line / wait_for_exit (POS: read-side views of jobs.)
- agent.meta_tools.bash._background.termination::leader_identity / own_identity (POS: group-level stop primitives; record a job leader's, and this server's, pid with its start stamp.)

[OUTPUT]
- BackgroundProcessRegistry: Process-wide singleton with per-session buckets,
  SIGTERM→SIGKILL grace escalation, 32 Ki-character line truncation, 300 s reap of
  exited entries, ``last_progress`` snapshot on ``BackgroundProcessInfo``,
  ``get_partial_line`` (the unfinished last line of a running job, computed per read)
  and ``kill_session_jobs`` for cooperative cleanup when an agent session
  is cancelled. A finished job whose children keep running stays listed with
  ``leftover_processes`` until they exit or ``kill`` stops them.
- get_background_registry: Lazy singleton accessor.

[POS]
PTC-adjacent runtime helper. Bash-tool only; no business-layer coupling.
"""

from __future__ import annotations

import asyncio
import atexit
import logging
import time
from collections import deque
from threading import Lock
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.bash._background.consume import (
    BackgroundRegistryEntry,
    consume_background_entry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.lifecycle import RegistryLifecycleMixin
from myrm_agent_harness.agent.meta_tools.bash._background.poll import snapshot_entry, unfinished_line, wait_for_exit
from myrm_agent_harness.agent.meta_tools.bash._background.termination import leader_identity, own_identity
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    OUTPUT_RING_LINES,
    WAIT_MAX_SECONDS,
    BackgroundProcessInfo,
    BackgroundQuotaError,
    FinishListener,
    OutputTail,
    ProgressListener,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.output_spill import (
        BackgroundOutputSpillWriter,
    )
    from myrm_agent_harness.toolkits.code_execution.executors.models import (
        AsyncProcessProtocol,
    )

logger = logging.getLogger(__name__)

_DEFAULT_PER_SESSION_LIMIT = 5  # Soft cap; raise via env if a power-user complains.
_DEFAULT_REAP_DELAY_SECONDS = 300.0  # Exited entries are purged from the registry after this idle window.


class BackgroundProcessRegistry(RegistryLifecycleMixin):
    """Process-wide registry of background bash jobs.

    Thread-safe under threading.Lock; reader tasks run on the event loop of
    the caller that registered them, which is fine because the registry only
    interacts with completed snapshots, not the running async I/O.
    """

    def __init__(
        self,
        *,
        per_session_limit: int = _DEFAULT_PER_SESSION_LIMIT,
        reap_delay_seconds: float = _DEFAULT_REAP_DELAY_SECONDS,
    ) -> None:
        self._entries = {}
        self._lock = Lock()
        self._per_session_limit = per_session_limit
        self._reap_delay_seconds = reap_delay_seconds

    async def register(
        self,
        proc: AsyncProcessProtocol,
        command: str,
        session_id: str | None,
        *,
        finish_listener: FinishListener | None = None,
        progress_listener: ProgressListener | None = None,
    ) -> BackgroundProcessInfo:
        pid = getattr(getattr(proc, "_proc", None), "pid", None)
        if pid is None:  # pragma: no cover — defensive
            raise RuntimeError("background process handle has no PID")
        # What a later signal compares with: whoever holds this pid then must be the process recorded now.
        leader = leader_identity(pid)

        with self._lock:
            active = sum(
                1 for e in self._entries.values() if e.info.session_id == session_id and e.info.status == "running"
            )
        if active >= self._per_session_limit:
            raise BackgroundQuotaError(session_id, self._per_session_limit)

        from myrm_agent_harness.agent.meta_tools.bash._background.job_store import (
            BackgroundJobStore,
            get_background_job_store,
        )
        from myrm_agent_harness.agent.meta_tools.bash._background.output_spill import (
            BackgroundOutputSpillWriter,
        )

        job_id = BackgroundJobStore.new_job_id()
        started_at = time.time()
        spill_writer: BackgroundOutputSpillWriter | None = None
        if session_id:
            spill_writer = BackgroundOutputSpillWriter(session_id=session_id, job_id=job_id)

        from myrm_agent_harness.agent.security.redact import redact_command_line

        sanitized_command = redact_command_line(command)

        info = BackgroundProcessInfo(
            job_id=job_id,
            pid=pid,
            command=sanitized_command,
            session_id=session_id,
            started_at=started_at,
            status="running",
            last_output_at=started_at,
        )
        entry = BackgroundRegistryEntry(
            info=info,
            proc=proc,
            stdout_buffer=deque(maxlen=OUTPUT_RING_LINES),
            stderr_buffer=deque(maxlen=OUTPUT_RING_LINES),
            finish_listener=finish_listener,
            progress_listener=progress_listener,
            spill_writer=spill_writer,
            leader=leader,
        )

        with self._lock:
            self._entries[pid] = entry

        store = get_background_job_store()
        if store is not None and session_id:
            try:
                store.insert_running(
                    job_id=job_id,
                    pid=pid,
                    session_id=session_id,
                    command=sanitized_command,
                    started_at=started_at,
                    owner=own_identity(),
                )
            except Exception as exc:
                logger.warning("Background job store insert failed job=%s: %s", job_id, exc)

        entry.reader_task = asyncio.create_task(self._consume(entry))
        return info

    def list_processes(self, session_id: str | None = None) -> list[BackgroundProcessInfo]:
        with self._lock:
            entries = list(self._entries.values())
        if session_id is None:
            return [snapshot_entry(e) for e in entries]
        return [snapshot_entry(e) for e in entries if e.info.session_id == session_id]

    def get(self, pid: int) -> BackgroundProcessInfo | None:
        with self._lock:
            entry = self._entries.get(pid)
        return snapshot_entry(entry) if entry else None

    def get_partial_line(self, pid: int) -> str:
        """The unfinished last line of a running job (usually its prompt), cleaned and redacted; empty otherwise.

        Computed at each read, not in the snapshot: ``wait`` and the auto-yield window poll the snapshot every
        100–250 ms, and cleaning and redacting the line on each poll would cost far more than the poll itself.
        """
        with self._lock:
            entry = self._entries.get(pid)
        if entry is None or entry.info.status != "running":
            return ""
        return unfinished_line(entry)

    def count_running(self, session_id: str | None = None) -> int:
        """Count running background jobs globally or for one session."""
        with self._lock:
            if session_id is None:
                return sum(1 for entry in self._entries.values() if entry.info.status == "running")
            return sum(
                1
                for entry in self._entries.values()
                if entry.info.session_id == session_id and entry.info.status == "running"
            )

    def get_output(self, pid: int, *, max_lines: int = 100) -> OutputTail:
        """Return the newest ``max_lines`` lines of each stream from the ring tail.

        ``dropped`` is ``True`` once a stream produced more lines than its ring holds: the oldest lines
        are gone from this view, so the caller knows the tail it got is not the whole output.
        """
        with self._lock:
            entry = self._entries.get(pid)
            if entry is None:
                return {"stdout": [], "stderr": [], "dropped": False}
            dropped = entry.output_dropped
            payload: OutputTail = {
                "stdout": list(entry.stdout_buffer)[-max_lines:],
                "stderr": list(entry.stderr_buffer)[-max_lines:],
                "dropped": dropped,
            }
            if dropped and entry.spill_writer is not None:
                spill_ref = entry.spill_writer.vault_log_ref
                if spill_ref:
                    payload["spill_log_ref"] = spill_ref
        return payload

    async def wait_for_process(
        self,
        pid: int,
        *,
        timeout_seconds: float,
    ) -> dict[str, object]:
        """Wait until a background job exits or ``timeout_seconds`` (capped at ``WAIT_MAX_SECONDS``) elapses."""
        return await wait_for_exit(self.get, pid, timeout_seconds=timeout_seconds, max_seconds=WAIT_MAX_SECONDS)

    async def write_stdin(
        self,
        pid: int,
        data: str,
        *,
        append_newline: bool = False,
        close: bool = False,
    ) -> dict[str, object]:
        """Send data to a running background process stdin (session-agnostic; callers must authorize)."""
        with self._lock:
            entry = self._entries.get(pid)
        if entry is None:
            return {"ok": False, "error": "not_found", "pid": pid}

        from myrm_agent_harness.agent.meta_tools.bash._background.stdin import (
            write_background_stdin,
        )

        return await write_background_stdin(
            entry,
            data,
            append_newline=append_newline,
            close=close,
        )

    async def _consume(self, entry: BackgroundRegistryEntry) -> None:
        await consume_background_entry(
            entry,
            snapshot=snapshot_entry,
            schedule_reap=self._schedule_reap,
            clear_session_if_idle=self._maybe_clear_session_spawn_tools,
        )


_registry: BackgroundProcessRegistry | None = None
_registry_lock = Lock()


def get_background_registry() -> BackgroundProcessRegistry:
    global _registry
    with _registry_lock:
        if _registry is None:
            _registry = BackgroundProcessRegistry()
            atexit.register(_registry.shutdown)
        return _registry


__all__ = [
    "BackgroundProcessInfo",
    "BackgroundProcessRegistry",
    "BackgroundQuotaError",
    "FinishListener",
    "ProgressListener",
    "get_background_registry",
]
