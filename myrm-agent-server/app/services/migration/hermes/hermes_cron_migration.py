"""Apply and rollback Hermes cron jobs during migration confirm.

[INPUT]
HermesCronMigrationPlan from dry-run session metadata.

[OUTPUT]
HermesCronApplyResult with created Myrm job ids for batch rollback.

[POS]
Server migration confirm hook — uses existing CronManager; jobs start paused.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.toolkits.cron.types import CronJob, CronJobPatch, JobStatus

from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager
from app.core.cron.adapters.setup import get_cron_manager
from .hermes_cron_converter import (
    HermesCronMigrationJobSpec,
    HermesCronMigrationPlan,
)

logger = logging.getLogger(__name__)

_MIGRATION_USER_ID = "default"


@dataclass(frozen=True, slots=True)
class HermesCronApplyResult:
    created_job_ids: tuple[str, ...]
    failed_count: int

    def to_metadata_dict(self) -> dict[str, object]:
        return {
            "created_job_ids": list(self.created_job_ids),
            "failed_count": self.failed_count,
        }

    @classmethod
    def from_metadata_dict(cls, raw: dict[str, object]) -> HermesCronApplyResult | None:
        ids_raw = raw.get("created_job_ids")
        if not isinstance(ids_raw, list):
            return None
        job_ids = tuple(str(item) for item in ids_raw if isinstance(item, str) and item.strip())
        failed_raw = raw.get("failed_count")
        failed_count = int(failed_raw) if isinstance(failed_raw, int) else 0
        return cls(created_job_ids=job_ids, failed_count=max(0, failed_count))


async def apply_hermes_cron_migration_plan(
    plan: HermesCronMigrationPlan,
    *,
    agent_id: str | None,
) -> HermesCronApplyResult:
    if not plan.importable:
        return HermesCronApplyResult(created_job_ids=(), failed_count=0)

    manager = get_cron_manager()
    created: list[str] = []
    failed = 0

    for spec in plan.importable:
        try:
            job = await _create_paused_job(manager, spec, agent_id=agent_id)
            created.append(job.id)
        except Exception as exc:
            failed += 1
            logger.warning(
                "Hermes cron migration skipped job %s (%s): %s",
                spec.source_hermes_id or spec.name,
                spec.name,
                exc,
            )

    return HermesCronApplyResult(created_job_ids=tuple(created), failed_count=failed)


async def rollback_hermes_cron_migration(raw: dict[str, object] | None) -> int:
    """Delete cron jobs created by a migration batch. Returns deleted count."""

    if not raw:
        return 0
    result = HermesCronApplyResult.from_metadata_dict(raw)
    if result is None or not result.created_job_ids:
        return 0

    manager = get_cron_manager()
    deleted = 0
    for job_id in result.created_job_ids:
        try:
            if await manager.delete_job(job_id, _MIGRATION_USER_ID):
                deleted += 1
        except Exception as exc:
            logger.warning("Hermes cron migration rollback failed for job %s: %s", job_id, exc)
    return deleted


async def _create_paused_job(
    manager: EntitlementGuardedCronManager,
    spec: HermesCronMigrationJobSpec,
    *,
    agent_id: str | None,
) -> CronJob:
    schedule = spec.to_schedule()
    job = await manager.create_job(
        _MIGRATION_USER_ID,
        spec.name,
        spec.job_type,
        schedule,
        prompt=spec.prompt,
        agent_id=agent_id,
        max_fires=spec.max_fires,
    )
    paused = await manager.update_job(
        job.id,
        _MIGRATION_USER_ID,
        CronJobPatch(status=JobStatus.PAUSED),
    )
    return paused or job
