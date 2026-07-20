"""Startup hook for durable background bash job store (BSDL Core).

[INPUT]
- app.services.context.context_assembly::ContextAssemblyService (POS: harness_dir)
- myrm_agent_harness.api.hooks::get_background_registry (POS: live pids)

[OUTPUT]
- init_background_job_store: Configure SQLite store + reconcile orphaned jobs

[POS]
Server startup — deploy grace: mark store running rows orphaned when registry empty.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_background_job_store() -> None:
    """Configure BackgroundJobStore on Volume and reconcile after process restart."""
    from myrm_agent_harness.api.hooks import (
        configure_background_job_store,
        get_background_job_store,
        get_background_registry,
    )

    try:
        from app.services.context.context_assembly import ContextAssemblyService

        facade = ContextAssemblyService.build_facade(ensure_layout=False)
        db_path = facade.harness_path() / ".myrm" / "background_jobs.db"
        configure_background_job_store(db_path)
    except Exception as exc:
        logger.warning("[Startup] BackgroundJobStore configuration skipped: %s", exc)
        return

    store = get_background_job_store()
    if store is None:
        return

    live_pids = frozenset(info.pid for info in get_background_registry().list_processes())
    orphaned = store.reconcile_running_jobs(live_pids)
    logger.info(
        "[Startup] BackgroundJobStore ready at %s (reconciled %d orphaned)",
        store.db_path,
        orphaned,
    )
