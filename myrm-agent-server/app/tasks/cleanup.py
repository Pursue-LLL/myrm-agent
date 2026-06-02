"""Task history cleanup cron job."""

import logging

from myrm_agent_harness.toolkits.tasks import TaskStore

logger = logging.getLogger(__name__)


async def cleanup_old_tasks(
    store: TaskStore,
    days: int = 30,
) -> int:
    """Clean up old completed tasks.

    Args:
        store: Task store
        days: Delete tasks older than this many days (default 30)

    Returns:
        Number of tasks deleted

    Notes:
        - Only deletes terminal status tasks (succeeded/failed/cancelled)
        - Should be run as periodic cron job (e.g., daily at 2am)
    """
    logger.info(f"Starting task cleanup (older than {days} days)...")

    try:
        deleted_count = await store.clean_old_tasks(days=days)
        logger.info(f"Task cleanup completed: {deleted_count} tasks deleted")
        return int(deleted_count)
    except Exception as e:
        logger.error(f"Task cleanup failed: {e}", exc_info=True)
        return 0


__all__ = ["cleanup_old_tasks"]
