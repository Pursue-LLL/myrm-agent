"""Read-only queries of the cron CRUD manager.

[INPUT]
- infra.incremental.types::MonitorState (POS: Domain types for incremental monitoring.)
- cron.protocols::CronStore (POS: cron job persistence protocol)
- cron.types::CronJob, CronRunRecord (POS: cron data models)

[OUTPUT]
- CronQueryMixin: job and run listings, counts and lookups, and the incremental-monitor state reads

[POS]
Query half of the cron CRUD manager, mixed into ``CronManager``. Reads go straight to the store; the rules of their
own are that job listings and counts are the user's jobs unless ``include_system`` asks for the application's own, and
that run records outlive a deleted job but are not served by its id.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.infra.incremental.types import MonitorState
    from myrm_agent_harness.toolkits.cron.protocols import CronStore
    from myrm_agent_harness.toolkits.cron.types import CronJob, CronRunRecord


class CronQueryMixin:
    """Job, run and monitor-state reads for ``CronManager``."""

    if TYPE_CHECKING:
        # Provided by the concrete manager that composes this mixin.
        _store: CronStore

    async def list_jobs(
        self,
        *,
        name_filter: str | None = None,
        chat_id: str | None = None,
        project_id: str | None = None,
        include_system: bool = False,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[CronJob]:
        """The user's jobs; ``include_system`` adds the jobs the application creates itself (the heartbeat)."""
        return await self._store.list_jobs(
            name_filter=name_filter,
            chat_id=chat_id,
            project_id=project_id,
            include_system=include_system,
            limit=limit,
            offset=offset,
        )

    async def count_jobs(
        self,
        *,
        name_filter: str | None = None,
        chat_id: str | None = None,
        project_id: str | None = None,
        include_system: bool = False,
    ) -> int:
        return await self._store.count_jobs(
            name_filter=name_filter,
            chat_id=chat_id,
            project_id=project_id,
            include_system=include_system,
        )

    async def get_job(self, job_id: str) -> CronJob | None:
        return await self._store.get_job(job_id)

    async def list_runs(
        self,
        *,
        job_id: str | None = None,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> list[CronRunRecord]:
        # Run records outlive a deleted job (a one-shot job is deleted after it ran) but are not served by its id.
        if job_id and await self._store.get_job(job_id) is None:
            return []
        return await self._store.list_runs(job_id, limit=limit, offset=offset, status=status)

    async def count_runs(
        self,
        *,
        job_id: str | None = None,
        status: str | None = None,
    ) -> int:
        if job_id and await self._store.get_job(job_id) is None:
            return 0
        return await self._store.count_runs(job_id, status=status)

    async def get_monitor_state(self, job_id: str) -> MonitorState | None:
        """Return the monitor state for a job, or None if not found."""
        return await self._store.get_monitor_state(job_id)

    async def batch_get_monitor_states(self, job_ids: list[str]) -> dict[str, MonitorState]:
        """Batch get monitor states for multiple jobs.

        Returns dict mapping job_id to MonitorState. Missing jobs are omitted.
        """
        return await self._store.batch_get_monitor_states(job_ids)
