"""[INPUT]
- .state (POS: shared startup state)

[OUTPUT]
- _shutdown

[POS]
Graceful shutdown of the server lifespan.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.core.memory.adapters.setup import shutdown_cached_memory_managers
from app.lifecycle import (
    shutdown_global_browser_pool,
    stop_approval_ttl_scheduler,
    stop_auth_alert_monitor,
    stop_auth_log_cleanup_scheduler,
    stop_cancellation_cleanup_scheduler,
    stop_context_cleanup_scheduler,
    stop_context_compaction_telemetry_dispatcher,
    stop_db_maintenance_scheduler,
    stop_kanban_dispatchers,
    stop_login_session_cleanup_scheduler,
    stop_memory_brief_status_telemetry_dispatcher,
    stop_memory_guardian_guard_telemetry_dispatcher,
    stop_memory_guardian_scheduler,
    stop_memory_pressure_monitor,
    stop_remote_backup_scheduler,
)
from app.server.shutdown import (
    safe_close_checkpointer,
    safe_close_external_agent_pools,
    safe_close_model_transport,
    safe_shutdown_observability,
    safe_stop_cron,
    safe_stop_gateway,
    safe_stop_maintenance_daemon,
    safe_stop_task_worker,
    safe_wait_background_tasks,
)
from app.services.agent.evolution.evolution_runtime import shutdown_evolution_runtime
from app.services.memory.imports.integration_sync_daemon import stop_integration_sync_daemon

if TYPE_CHECKING:
    pass

from . import state
from .state import logger


async def _shutdown(app_instance: FastAPI) -> None:
    """Graceful shutdown: drain in-flight Agent turns, then stop all components."""
    # First, before the (slow) drain: the desktop shell only waits seconds for a self-exit and
    # takes the curtain down with it, so a lease still held would leave the Mac unlocked and uncovered.
    try:
        from app.services.locked_use.unattended import stop_unattended_curtain_watcher

        await stop_unattended_curtain_watcher()
    except Exception as e:
        logger.error("[Shutdown] Unattended curtain watcher stop failed: %s", e)

    try:
        from app.services.agent.goals.usage_limit_resume import get_usage_limit_wake_daemon

        await get_usage_limit_wake_daemon().stop()
    except Exception as e:
        logger.error("[Shutdown] Usage-limit wake daemon stop failed: %s", e)

    try:
        from app.services.sandbox_wake import get_wake_schedule_reporter

        await get_wake_schedule_reporter().stop()
    except Exception as e:
        logger.error("[Shutdown] Wake schedule reporter stop failed: %s", e)

    try:
        from app.services.agent.gateway import get_agent_gateway

        gateway = get_agent_gateway()
        if not gateway.is_draining:
            await gateway.begin_drain()
    except Exception as e:
        logger.error("[Shutdown] Agent gateway drain failed: %s", e)

    try:
        from app.remote_access.tunnel_manager import get_tunnel_manager

        await get_tunnel_manager().shutdown()
        logger.info("[Shutdown] Cloudflare tunnel stopped")
    except Exception as e:
        logger.error("[Shutdown] Tunnel shutdown failed: %s", e)

    frontend_launcher = getattr(app_instance.state, "frontend_launcher", None)
    if frontend_launcher is not None:
        try:
            frontend_launcher.stop()
            logger.info("[Shutdown] Frontend server stopped")
        except Exception as e:
            logger.error("[Shutdown] Frontend stop failed: %s", e)

    if state._context_cleanup_scheduler_instance is not None:
        try:
            await state._context_cleanup_scheduler_instance.stop()
        except Exception as e:
            logger.error("[Shutdown] Context cleanup task stop failed: %s", e)

    try:
        from app.services.agent.goals.goal_branch_stash import stop_branch_watcher

        stop_branch_watcher()
    except Exception as e:
        logger.error("[Shutdown] Branch watcher stop failed: %s", e)

    try:
        from app.core.skills.curator.service import stop_curator_background_task

        stop_curator_background_task()
    except Exception as e:
        logger.error("[Shutdown] Curator background task stop failed: %s", e)

    try:
        from app.services.skills.nightly_review.service import stop_nightly_review_task

        stop_nightly_review_task()
    except Exception as e:
        logger.error("[Shutdown] Nightly review task stop failed: %s", e)

    try:
        from app.lifecycle.harness_bridge import stop_harness_bridge

        harness_bridge_task = stop_harness_bridge()
    except ImportError:

        async def _dummy() -> None:
            pass

        harness_bridge_task = _dummy()

    async def _shutdown_mcp() -> None:
        from app.api.mcp import shutdown_mcp_endpoint

        await shutdown_mcp_endpoint()

    async def _stop_extract_retry_worker() -> None:
        from app.services.memory.extract_retry.extract_retry_worker import (
            extract_retry_worker,
        )

        await extract_retry_worker.stop()

    async def _stop_lifecycle_webhook_service() -> None:
        from app.services.webhook.lifecycle_webhook_service import (
            LifecycleOutboundWebhookService,
        )

        await LifecycleOutboundWebhookService.get_instance().stop()

    shutdown_results = await asyncio.gather(
        safe_stop_cron(),
        safe_stop_gateway(),
        stop_kanban_dispatchers(),
        shutdown_global_browser_pool(),
        safe_close_checkpointer(state._checkpointer_cleanup),
        safe_close_external_agent_pools(),
        stop_auth_alert_monitor(),
        stop_auth_log_cleanup_scheduler(),
        stop_context_compaction_telemetry_dispatcher(),
        stop_memory_brief_status_telemetry_dispatcher(),
        stop_memory_guardian_guard_telemetry_dispatcher(),
        stop_context_cleanup_scheduler(),
        stop_db_maintenance_scheduler(),
        stop_login_session_cleanup_scheduler(),
        stop_approval_ttl_scheduler(),
        stop_cancellation_cleanup_scheduler(),
        stop_memory_guardian_scheduler(),
        shutdown_cached_memory_managers(),
        stop_memory_pressure_monitor(),
        stop_remote_backup_scheduler(),
        safe_stop_task_worker(),
        safe_stop_maintenance_daemon(),
        safe_wait_background_tasks(),
        safe_shutdown_observability(),
        shutdown_evolution_runtime(),
        stop_integration_sync_daemon(),
        harness_bridge_task,
        _shutdown_mcp(),
        _stop_extract_retry_worker(),
        _stop_lifecycle_webhook_service(),
        return_exceptions=True,
    )
    for r in shutdown_results:
        if isinstance(r, Exception):
            logger.error("[Shutdown] Component stop failed: %s", r)

    # After the gather: the background tasks it waited for (skill review, memory extraction) still call models.
    await safe_close_model_transport()

    # Final: WAL checkpoint + engine dispose to ensure all data is flushed to disk
    try:
        from app.platform_utils import get_database_engine

        engine = get_database_engine()
        try:
            async with engine.begin() as conn:
                # Use TRUNCATE to flush dirty WAL pages into main DB and reset WAL file to 0 bytes,
                # eliminating torn write risks upon process exit or cold restart. Fall back to PASSIVE if locked.
                try:
                    await conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
                except Exception:
                    await conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception as e:
            logger.warning("[Shutdown] Database WAL checkpoint failed (ignoring): %s", e)
        await engine.dispose()
        logger.info("[Shutdown] Database engine disposed")

        from app.database.operations.backup import get_sqlite_backup_manager

        manager = get_sqlite_backup_manager()
        if manager is not None:
            manager.create_backup()
    except Exception as e:
        logger.error("[Shutdown] Database backup failed: %s", e)
