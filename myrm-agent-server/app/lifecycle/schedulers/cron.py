"""[INPUT]
- app.services / app.core schedulers (POS: the schedulers this module starts)

[OUTPUT]
- start_cron_scheduler

[POS]
Lifecycle schedulers: the cron scheduler start hook.
"""

from __future__ import annotations

from .common import _MONITOR_CLEANUP_BATCH_SIZE, _MONITOR_STARTUP_MAX_BATCHES, logger


async def start_cron_scheduler() -> None:
    """启动 Cron Scheduler（定时任务调度器）"""
    from app.core.cron.adapters.setup import get_cron_scheduler, get_cron_store

    try:
        cleanup_stats = await get_cron_store().normalize_monitor_configs_batch(
            batch_size=_MONITOR_CLEANUP_BATCH_SIZE,
            max_batches=_MONITOR_STARTUP_MAX_BATCHES,
        )
        if cleanup_stats.normalized_count > 0:
            logger.info(
                "Cron startup cleanup normalized %d legacy monitor_config payloads",
                cleanup_stats.normalized_count,
            )
        if cleanup_stats.continuation_required:
            logger.info(
                "Cron startup monitor_config cleanup has remaining rows; continuation required (scanned=%d, batches=%d)",
                cleanup_stats.scanned_count,
                cleanup_stats.processed_batches,
            )
    except Exception as exc:
        logger.warning("Cron startup monitor_config cleanup failed: %s", exc)

    try:
        from app.services.onboarding.second_brain_preset import (
            reconcile_second_brain_cron_ids,
        )
        from app.services.wiki.source_sync.read_it_later_hygiene import (
            migrate_stale_read_it_later_jobs,
        )

        hygiene = await migrate_stale_read_it_later_jobs()
        if hygiene.migrated_count:
            logger.info(
                "Cron startup migrated %d stale read-it-later job(s)",
                hygiene.migrated_count,
            )
        await reconcile_second_brain_cron_ids(hygiene.id_remaps)
    except Exception as exc:
        logger.warning("Cron startup read-it-later hygiene failed: %s", exc)

    try:
        from app.services.onboarding.second_brain_preset import (
            repair_wiki_delta_job_security,
        )

        await repair_wiki_delta_job_security()
    except Exception as exc:
        logger.warning("Cron startup wiki-delta job repair failed: %s", exc)

    await get_cron_scheduler().start()
    logger.info("Cron scheduler started")
