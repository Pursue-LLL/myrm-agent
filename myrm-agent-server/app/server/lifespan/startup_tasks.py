"""[INPUT]
- .state (POS: shared startup state)
- app.ai_agents.general_agent.tools::ensure_tool_layer_bootstrap (POS: tool package facade that defers the heavy tool layer registration to first use or background warmup)
- app.services.workflow_templates.service::get_template_store (POS: server-side adapter for workflow template persistence)
- app.services.workflow_templates.trunk_templates::seed_trunk_templates (POS: server-owned business content for the Dynamic Workflow engine)
- myrm_agent_harness.toolkits.code_execution.config::set_execution_config (POS: code execution configuration layer)

[OUTPUT]
- the boot tasks: DB pool metrics registration, the @startup event, the agent tool layer preload, trunk template seeding and the code execution config

[POS]
Boot tasks that stand alone: the startup phases run the DB pool metrics registration and the code execution config, and the background start spawns the @startup event, the tool layer preload and the trunk template seeding after the first screen.
"""

from __future__ import annotations

import asyncio

from app.config.settings import settings

from .state import logger


async def _register_db_pool_metrics_task() -> None:
    """Delegate DB pool metrics registration to MonitoringManager."""
    from app.core.monitoring import register_db_pool_metrics

    await register_db_pool_metrics()


async def _dispatch_startup_event() -> None:
    """Dispatch @startup system event so trigger-bound cron jobs can fire on boot."""
    try:
        from app.core.cron.adapters.setup import get_cron_scheduler

        scheduler = get_cron_scheduler()
        if scheduler:
            count = await scheduler.dispatch_system_event(source="app", event_type="startup", payload={})
            if count:
                logger.info("[Startup] @startup trigger fired %d job(s)", count)
    except Exception as e:
        logger.debug("[Startup] @startup event dispatch skipped: %s", e)


async def _preload_agent_tool_layers() -> None:
    """Register server-layer tools off the boot path; the first agent turn awaits the same gate."""
    try:
        from app.ai_agents.general_agent.tools import ensure_tool_layer_bootstrap

        await asyncio.to_thread(ensure_tool_layer_bootstrap)
        logger.info("[Startup] Agent tool layers ready")
    except Exception as exc:
        logger.exception("[Startup] Agent tool layer preload failed: %s", exc)


async def _seed_trunk_templates() -> None:
    """Insert missing trunk templates in the background; boot never waits on it."""
    try:
        from app.services.workflow_templates.service import get_template_store
        from app.services.workflow_templates.trunk_templates import seed_trunk_templates

        def _seed() -> int:
            return len(seed_trunk_templates(get_template_store()))

        ready = await asyncio.to_thread(_seed)
        logger.info("[Startup] Trunk workflow templates ready: %d", ready)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Startup] Trunk template seeding skipped: %s", exc)


def _apply_code_execution_config() -> None:
    """Apply business-layer code execution configuration to the framework."""
    from myrm_agent_harness.toolkits.code_execution.config import (
        ExecutionConfig,
        NetworkConfig,
        set_execution_config,
    )

    ce = settings.code_execution
    allowed_hosts: frozenset[str] | None = None
    if ce.allowed_hosts:
        allowed_hosts = frozenset(h.strip() for h in ce.allowed_hosts.split(",") if h.strip())

    config = ExecutionConfig(
        network=NetworkConfig(
            allow_network=ce.allow_network,
            allowed_hosts=allowed_hosts,
        ),
    )
    set_execution_config(config)
    logger.info(
        "Code execution config applied: allow_network=%s, allowed_hosts=%s",
        ce.allow_network,
        "default" if allowed_hosts is None else len(allowed_hosts),
    )
