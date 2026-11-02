"""Stop, reap and shutdown behaviour of the background job registry.

``kill`` stops a job and everything it started, or only what a finished job left behind; ``kill_session_jobs`` ends a
cancelled session's running jobs concurrently; finished entries are reaped after a delay that is deferred while their
leftovers run; ``shutdown`` is the ``atexit`` sweep over the groups of running jobs and of finished jobs that left
something running. A job whose leader pid another process now holds is left alone by ``kill`` and ``shutdown``.

[INPUT]
- agent.meta_tools.bash._background.consume::BackgroundRegistryEntry (POS: live registry row with ring buffers, spill writer, the leader's recorded identity and the processes the job left running)
- agent.meta_tools.bash._background.termination::stop_job / stop_leftovers / refresh_leftovers / signal_group_if_ours (POS: group-level stop primitives)
- agent.meta_tools.bash._background.store_sync::persist_terminal_state (POS: write-through persistence of a job's terminal state to the ledger)
- agent.meta_tools.bash._background.session_spawn_lifecycle::clear_session_spawn_tools (POS: thread-safe in-process store for spawn/cleanup coordination)
- utils.os_compat::SIGKILL (POS: cross-platform process-group control)

[OUTPUT]
- RegistryLifecycleMixin: ``kill`` / ``kill_session_jobs`` / reap scheduling / ``shutdown`` for the registry that holds ``_entries``

[POS]
Mixed into BackgroundProcessRegistry, which owns the entry table and the lock these methods work under.
"""

from __future__ import annotations

import asyncio
import logging
from threading import Lock
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.meta_tools.bash._background.termination import (
    refresh_leftovers,
    signal_group_if_ours,
    stop_job,
    stop_leftovers,
)
from myrm_agent_harness.utils.os_compat import SIGKILL

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.consume import BackgroundRegistryEntry

logger = logging.getLogger(__name__)

_DEFAULT_KILL_GRACE_SECONDS = 5.0  # SIGTERM → SIGKILL escalation window.


class RegistryLifecycleMixin:
    """Lifecycle half of ``BackgroundProcessRegistry``."""

    _entries: dict[int, BackgroundRegistryEntry]
    _lock: Lock
    _reap_delay_seconds: float

    async def kill(
        self,
        pid: int,
        *,
        force: bool = False,
        grace_seconds: float = _DEFAULT_KILL_GRACE_SECONDS,
    ) -> bool:
        """Stop a background job and everything it started, escalating SIGTERM → SIGKILL if needed.

        Signals target the whole process group (POSIX ``killpg`` / Windows
        ``taskkill /T /F``) so forked children (``esbuild`` / ``node``) die
        with the parent and free their ports. With ``force=False`` the
        registry waits up to ``grace_seconds`` (one budget for the leader and
        everything it started) and upgrades to SIGKILL on timeout, which
        evicts programs that ignore SIGTERM.
        A job that already finished is only asked to stop what it left behind,
        and a job whose leader pid another process now holds is not signalled.
        Whatever outlives the kill stays recorded on the entry
        (``BackgroundProcessInfo.leftover_processes``) rather than being
        reported as stopped. Returns ``False`` only for an unknown ``pid``.
        """
        with self._lock:
            entry = self._entries.get(pid)
        if entry is None:
            return False
        info = entry.info
        if info.status != "running":
            entry.leftover_members = await stop_leftovers(
                info.pid, entry.leftover_members, entry.leader, force=force, grace_seconds=grace_seconds
            )
            return True

        # Marked before the first signal: the reader flips a still-running job
        # to ``exited`` the moment it sees the leader go, and a job the caller
        # stopped must reach the finish listener as ``killed``.
        info.status = "killed"
        entry.leftover_members = await stop_job(entry, force=force, grace_seconds=grace_seconds)

        # The reader task drains any tail output and invokes the finish
        # listener via ``_consume``'s ``finally`` block.
        from myrm_agent_harness.agent.meta_tools.bash._background.store_sync import (
            persist_terminal_state,
        )

        persist_terminal_state(info)
        if entry.reader_task and not entry.reader_task.done():
            entry.reader_task.cancel()
        return True

    async def kill_session_jobs(
        self,
        session_id: str,
        *,
        grace_seconds: float = _DEFAULT_KILL_GRACE_SECONDS,
    ) -> int:
        """Terminate every running background job owned by ``session_id``.

        Invoked by the server when an agent stream is cancelled (user Stop,
        budget exhausted, PWA disconnect grace expiry) so that the
        long-running shells it started (``npm install``, ``webpack --watch``)
        are stopped instead of left to eat RAM / CPU / sandbox quota; what
        outlives a stop stays recorded on the entry (see ``kill``). Returns
        the number of those jobs ``kill`` accepted.

        Kills dispatch *concurrently* via ``asyncio.gather`` so worst-case
        latency is bounded by a single ``grace_seconds`` window rather than
        ``N × grace_seconds``. We snapshot pid+status inside the lock to
        avoid mutating ``self._entries`` while the iterator is live; the
        actual ``kill`` runs lock-free.
        """
        with self._lock:
            targets = [
                entry.info.pid
                for entry in self._entries.values()
                if entry.info.session_id == session_id and entry.info.status == "running"
            ]
        if not targets:
            self._maybe_clear_session_spawn_tools(session_id)
            return 0

        results = await asyncio.gather(
            *(self.kill(pid, grace_seconds=grace_seconds) for pid in targets),
            return_exceptions=True,
        )
        killed = sum(1 for r in results if r is True)
        if killed:
            logger.info(
                "background: cancelled session=%s killed=%d/%d jobs (grace=%.1fs)",
                session_id,
                killed,
                len(targets),
                grace_seconds,
            )
        self._maybe_clear_session_spawn_tools(session_id)
        return killed

    def _maybe_clear_session_spawn_tools(self, session_id: str | None) -> None:
        """Drop spawn lifecycle markers when a session has no running shell jobs."""
        if not session_id:
            return
        with self._lock:
            has_running = any(
                entry.info.session_id == session_id and entry.info.status == "running"
                for entry in self._entries.values()
            )
        if has_running:
            return
        from myrm_agent_harness.agent.meta_tools.bash._background.session_spawn_lifecycle import (
            clear_session_spawn_tools,
        )

        clear_session_spawn_tools(session_id)

    def _schedule_reap(self, pid: int) -> None:
        """Drop an exited/killed entry after a short window so ``list_processes``
        doesn't accumulate history (caps token cost on long sessions).
        """
        if self._reap_delay_seconds <= 0:
            self._pop_finished_entry(pid)
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # pragma: no cover — no loop = test setup
            self._pop_finished_entry(pid)
            return
        loop.call_later(self._reap_delay_seconds, self._reap_entry, pid)

    def _reap_entry(self, pid: int) -> None:
        """Reap timer callback: a finished job whose children still run stays listed.

        The entry is the only handle through which the user can stop those
        children, so the reap is deferred until they exit.
        """
        with self._lock:
            entry = self._entries.get(pid)
        if entry is not None and refresh_leftovers(entry):
            self._schedule_reap(pid)
            return
        self._pop_finished_entry(pid)

    def _pop_finished_entry(self, pid: int) -> None:
        with self._lock:
            entry = self._entries.get(pid)
            # A finished job is ``exited`` (the reader saw it end) or ``killed``
            # (``kill`` marked it), so ``running`` here means a newer job took
            # over this pid.
            if entry is None or entry.info.status == "running":
                return
            self._entries.pop(pid, None)

    def shutdown(self) -> None:
        """Group-SIGKILL, on interpreter exit, every running job and every finished job that left a live member.

        Mirrors the ``kill`` contract so forked grandchildren
        (``node`` / ``esbuild`` under ``npm start``) die with the leader, and
        covers what finished jobs left running. A job whose leader pid
        another process now holds is skipped. ``atexit`` is synchronous;
        live callers should use ``kill`` for grace.
        """
        with self._lock:
            entries = list(self._entries.values())
        for entry in entries:
            if entry.info.status != "running" and not refresh_leftovers(entry):
                continue
            signal_group_if_ours(entry.info.pid, entry.leader, SIGKILL)
