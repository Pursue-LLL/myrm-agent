"""Integration Sync Daemon — scheduled background sync for knowledge sources.

[INPUT]
- app.services.memory.integration_memory (POS: IntegrationMemoryService facade)
- app.core.channel_bridge.config_loader (POS: User config loader with TTL cache)
- app.core.channel_bridge.config_parsers (POS: MCP config parser)
- myrm_agent_harness.toolkits.mcp.connection_manager (POS: MCP connection pool)
- apscheduler (POS: Async scheduler for periodic tasks)

[OUTPUT]
- start_integration_sync_daemon / stop_integration_sync_daemon: Lifecycle API.

[POS]
Reuses the APScheduler pattern already established in schedulers.py for
DB maintenance, context cleanup, etc.  On each tick, dynamically discovers
user-configured MCP servers, registers eligible ones as MCPBridgeProviders,
then invokes IntegrationMemoryService.sync_all() to keep knowledge sources fresh.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.memory.integration_memory import IntegrationMemoryService

logger = logging.getLogger(__name__)

_DEFAULT_INTERVAL_MINUTES = 60

_daemon_task: asyncio.Task[None] | None = None


async def _sync_job() -> None:
    """Execute a full sync of all registered integration providers.

    On each tick the daemon dynamically discovers user-configured MCP servers,
    wraps eligible ones as MCPBridgeProvider instances, and registers them with
    the IntegrationMemoryService before triggering sync_all().
    """
    try:
        from app.services.memory.integration_memory import get_integration_memory_service

        svc = await get_integration_memory_service()
        if svc is None:
            return

        await _register_mcp_providers(svc)

        if not svc.provider_ids:
            return

        results = await svc.sync_all()
        total_created = sum(r.created for r in results)
        total_errors = sum(r.failed for r in results)

        if total_created > 0 or total_errors > 0:
            logger.info(
                "Integration sync completed: providers=%d, created=%d, errors=%d",
                len(results),
                total_created,
                total_errors,
            )
    except Exception as exc:
        logger.warning("Integration sync job failed: %s", exc)


async def _register_mcp_providers(
    svc: IntegrationMemoryService,
) -> None:
    """Load user MCP configs and register eligible ones as MCPBridgeProviders.

    Providers whose ``provider_id`` is already registered are skipped to avoid
    duplicate registrations.  Servers without a suitable fetch tool are silently
    ignored by MCPBridgeProvider._detect_fetch_tool().
    """
    try:
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import extract_mcp_configs

        user_cfgs = await load_user_configs()
        mcp_configs = extract_mcp_configs(user_cfgs.mcp_dict)
        if not mcp_configs:
            return

        from myrm_agent_harness.toolkits.mcp.connection_manager import get_mcp_connection

        from app.services.memory.mcp_bridge_provider import MCPBridgeProvider

        existing_ids = set(svc.provider_ids)
        conn = await get_mcp_connection(mcp_configs)

        for cfg in mcp_configs:
            provider_id = f"mcp:{cfg.name}"
            if provider_id in existing_ids:
                continue
            provider = MCPBridgeProvider(
                server_name=cfg.name,
                connection=conn,
                display=cfg.description or cfg.name,
            )
            svc.register_provider(provider)
            logger.info("Registered MCPBridgeProvider: %s", provider_id)
    except Exception as exc:
        logger.warning("MCP provider registration failed: %s", exc)


async def start_integration_sync_daemon(interval_minutes: int = _DEFAULT_INTERVAL_MINUTES) -> None:
    """Start the background sync daemon with APScheduler."""
    global _daemon_task

    try:
        from apscheduler import AsyncScheduler
        from apscheduler.triggers.interval import IntervalTrigger

        async def run_scheduler() -> None:
            async with AsyncScheduler() as scheduler:
                await scheduler.add_schedule(
                    _sync_job,
                    IntervalTrigger(minutes=interval_minutes),
                    id="integration_knowledge_sync",
                )
                logger.info("Integration sync daemon started (every %d min)", interval_minutes)
                await asyncio.Event().wait()

        _daemon_task = asyncio.create_task(run_scheduler())

    except Exception as exc:
        logger.error("Failed to start integration sync daemon: %s", exc)


async def stop_integration_sync_daemon() -> None:
    """Stop the background sync daemon gracefully."""
    global _daemon_task

    if _daemon_task is None:
        return

    try:
        _daemon_task.cancel()
        try:
            await _daemon_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Integration sync daemon stopped")
    except Exception as exc:
        logger.error("[Shutdown] Integration sync daemon stop failed: %s", exc)
    finally:
        _daemon_task = None
