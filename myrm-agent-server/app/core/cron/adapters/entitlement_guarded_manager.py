"""CronManager wrapper — enforces sandbox cron entitlements on job mutations.

All create/duplicate paths (REST + agent ``cron_manage_tool``) go through
``get_cron_manager()``; slot checks live here instead of duplicating in routes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from myrm_agent_harness.toolkits.cron.types import CronJob

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.manager import CronManager


class EntitlementGuardedCronManager:
    """Delegates to harness ``CronManager``; gates ``create_job`` / ``duplicate_job``."""

    def __init__(self, inner: CronManager) -> None:
        self._inner = inner

    async def _enforce_slot(self, user_id: str) -> None:
        from app.platform_utils.sandbox.entitlements.entitlement_guard import (
            EntitlementGuardError,
            require_cron_slot,
        )

        try:
            current_count = await self._inner.count_jobs(user_id)
            require_cron_slot(current_count)
        except EntitlementGuardError as exc:
            raise ValueError(str(exc)) from exc

    async def create_job(self, user_id: str, *args: Any, **kwargs: Any) -> CronJob:
        await self._enforce_slot(user_id)
        return await self._inner.create_job(user_id, *args, **kwargs)

    async def duplicate_job(self, job_id: str, user_id: str) -> CronJob | None:
        await self._enforce_slot(user_id)
        return await self._inner.duplicate_job(job_id, user_id)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
