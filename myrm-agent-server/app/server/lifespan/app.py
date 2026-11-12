"""[INPUT]
- .startup / .shutdown (POS: lifespan phases)
- .background::schedule_background_work (POS: starts the boot's background tasks once uvicorn accepts connections)
- app.lifecycle (POS: channel gateway, cron and remote backup schedulers, kanban dispatch preparation)
- app.startup.desktop_path::hydrate_desktop_path (POS: recovers the login-shell PATH for a GUI-launched desktop sidecar)

[OUTPUT]
- optimized_lifespan

[POS]
The FastAPI lifespan: runs the sequential and parallel startup phases, schedules the background work for after the
socket bind, then shutdown.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from myrm_agent_harness.runtime.survival.startup import StartupTimer

from app.config.settings import settings
from app.lifecycle import (
    prepare_kanban_dispatch,
    start_channel_gateway,
    start_cron_scheduler,
    start_remote_backup_scheduler,
)

from . import startup
from .background import schedule_background_work
from .shutdown import _shutdown
from .state import logger


@asynccontextmanager
async def optimized_lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle manager with startup performance optimization.

    Everything before the ``yield`` delays the socket bind (uvicorn binds after the lifespan startup returns), so
    slow work stays off this path.

    Startup:
        Prelude:                           Desktop PATH completion (login-shell probe on a worker thread, awaited
                                            before phase 1b) → TLS compatibility → sandbox validation (when the
                                            deployment runs it) → Python environment reset
        Phase 1a (Critical - Sequential):  Persistent Root (local dev) → Pending Instance Swap →
                                            Database (with rescue) → Compression Streak Store → SaaS Provider Seed →
                                            DB Pool Metrics → Feature Flags → Config Migration →
                                            Provider Key Consolidation → Retired Provider OAuth Purge →
                                            Subscription Token Refresher → TLS Config → Privacy Policy →
                                            Control Plane SSRF Policy
        Phase 1b (Critical - Parallel):    Managed Approval Policy (synchronous), then Code Exec Config ‖
                                            Checkpointer ‖ State Manager ‖ Allowlist Store ‖ Workspace Trust Store ‖
                                            Permission Logger ‖ Context Cleanup ‖ Idle Handlers ‖ Prebuilt Skills ‖
                                            Built-in Agents ‖ Harness Bridge ‖ Security Reviewer ‖ Vault Credentials ‖
                                            Wiki Vault
        Phase 1.5 (Observability):         Monitoring → orphan eval workspace sweep → expired migration upload sweep
        Phase 2  (Essential):              Lifecycle Outbound Webhook → Maintenance Daemon (spillover and
                                            channel-image sweeps queued) → Channel Gateway ‖ Cron Scheduler ‖
                                            Remote Backup Scheduler ‖ Kanban Dispatch Preparation (boot recovery,
                                            runner wiring)
        Then, in order:                    Channel Routes → MCP Memory Endpoint → Memory Extract Retry Worker →
                                            Branch Watcher → Unattended Curtain Watcher → Usage-Limit Wake Daemon →
                                            Wake Schedule Reporter → Channel Budget Guards
        Phase 3  (Background - Async):     Warmup (schedulers, browser pool, batch recovery, tokenizer, risk rules,
                                            vector cache and more; see ``warmup``) ‖ Orphaned Goals ‖
                                            Kanban Dispatchers ‖ @startup Events ‖ Trunk Templates ‖
                                            Agent Tool Layers ‖ Route Groups (the routers no request has needed yet;
                                            started once the socket is bound; see ``background``)

    Shutdown (see ``shutdown``):
        1. Cancel the delayed background start; stop the curtain watcher and the wake daemons
        2. Drain the agent gateway; stop the tunnel, the frontend server and the periodic background tasks
        3. Stop in parallel: Cron ‖ Channel Gateway ‖ Kanban Dispatchers ‖ Browser Pool ‖ Checkpointer ‖
           Schedulers ‖ Workers ‖ MCP Endpoint ‖ the remaining components
        4. Close the model transport, then the database (WAL checkpoint, engine dispose, backup)
    """

    print(f"🐍 Python {sys.version.split()[0]}")

    # The login-shell probe waits on a child process (about a second with a heavy rc file), so it runs beside phase 1a
    # (database, migrations) and is awaited before phase 1b, the first to spawn a child process or check skill
    # `requires.bins` against PATH.
    from app.startup.desktop_path import hydrate_desktop_path

    path_hydration = asyncio.create_task(asyncio.to_thread(hydrate_desktop_path))

    from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation

    if apply_global_tls_relaxation():
        logger.info("[Startup] Enterprise TLS compatibility enabled (MYRM_TLS_STRICT=0)")

    timer = StartupTimer()
    logger.info("[Startup] Application starting...")

    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if get_deployment_capabilities().runs_sandbox_startup_validation:
        settings.validate_for_sandbox()

    # Reset requested from the cloud settings page before this container was recreated. It must run before any
    # component can create or cache the shared Python environment, so it precedes every startup phase.
    try:
        from app.services.infra.python_env_reset import apply_pending_python_env_reset

        if await asyncio.to_thread(apply_pending_python_env_reset):
            logger.info("[Startup] Shared Python environment reset as requested")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Startup] Python environment reset skipped: %s", exc)

    # === Phase 1: Critical tasks ===
    async with timer.phase("critical"):
        await startup._phase_1a_sequential()
        await path_hydration
        await startup._phase_1b_parallel()

    # === Phase 1.5: Observability setup ===
    async with timer.phase("monitoring"):
        from app.core.monitoring import setup_monitoring

        setup_monitoring(app_instance)

    # Orphan eval workspace sweep: eval runs are in-process background tasks,
    # so any leftover session workspace at boot is guaranteed stale. Cleared
    # synchronously before the HTTP server accepts eval requests.
    try:
        from app.core.eval.executor import cleanup_orphan_eval_workspaces

        removed = await asyncio.to_thread(cleanup_orphan_eval_workspaces)
        if removed:
            logger.info("[Startup] Removed %d orphan eval workspace(s)", removed)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Startup] Orphan eval workspace sweep skipped: %s", exc)

    # Migration ZIP extraction directories expire with their review session; at
    # boot none of them can still be in use, so stale ones are reclaimed here.
    try:
        from app.services.migration.source.source_payload_loader import (
            sweep_stale_migration_uploads,
        )

        stale_uploads = await asyncio.to_thread(sweep_stale_migration_uploads)
        if stale_uploads:
            logger.info("[Startup] Reclaimed %d expired migration upload(s)", stale_uploads)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Startup] Migration upload sweep skipped: %s", exc)

    # === Phase 2: Essential services ===
    async with timer.phase("core"):
        from app.services.background.daemon import maintenance_daemon
        from app.services.webhook.lifecycle_webhook_service import (
            LifecycleOutboundWebhookService,
        )

        LifecycleOutboundWebhookService.get_instance().start()

        await maintenance_daemon.start()

        # ContextGuard ephemeral transient spillover housekeeping (24h TTL)
        try:
            from app.services.agent.context_guard_service import ContextGuardService

            async def _sweep_spillover_task() -> None:
                await asyncio.to_thread(ContextGuardService.sweep_all_workspaces)

            maintenance_daemon.submit(_sweep_spillover_task)
            logger.info("[Startup] Enqueued initial ContextGuard spillover housekeeping task")
        except Exception as sweep_exc:
            logger.warning("[Startup] ContextGuard initial sweep enqueue skipped: %s", sweep_exc)

        # Expired channel images: the 03:00 job never runs on a machine that is off then.
        try:
            from app.channels.media.image_enrichment import sweep_channel_image_cache_at_startup

            maintenance_daemon.submit(sweep_channel_image_cache_at_startup)
        except Exception as sweep_exc:
            logger.warning("[Startup] Channel image cache sweep enqueue skipped: %s", sweep_exc)

        gw_result, cron_result, kanban_result, backup_result = await asyncio.gather(
            start_channel_gateway(),
            start_cron_scheduler(),
            prepare_kanban_dispatch(),
            start_remote_backup_scheduler(),
            return_exceptions=True,
        )

        if isinstance(gw_result, Exception):
            logger.error("[Startup] Channel Gateway failed to start: %s", gw_result)
        if isinstance(cron_result, Exception):
            logger.error("[Startup] Cron scheduler failed to start: %s", cron_result)
        if isinstance(kanban_result, Exception):
            logger.error("[Startup] Kanban dispatch preparation failed: %s", kanban_result)
        if isinstance(backup_result, Exception):
            logger.error("[Startup] Remote backup scheduler failed to start: %s", backup_result)

    try:
        from app.core.channel_bridge import init_channel_routes

        init_channel_routes(app_instance)
        logger.info("[Startup] Dynamic channel routes initialized")
    except Exception as e:
        logger.error("[Startup] Dynamic channel routes initialization failed: %s", e)

    # MCP memory endpoint for external agents
    try:
        from app.api.mcp import setup_mcp_endpoint

        await setup_mcp_endpoint(app_instance)
    except Exception as e:
        logger.warning("[Startup] MCP endpoint setup skipped: %s", e)

    logger.info(f"[Startup] Core services and routes ready: {timer.metrics.to_dict()}")

    try:
        from app.services.memory.extract_retry.extract_retry_worker import (
            extract_retry_worker,
        )

        await extract_retry_worker.start()
    except Exception as e:
        logger.error("[Startup] Memory extract retry worker failed to start: %s", e)

    try:
        from app.services.agent.goals.goal_branch_stash import start_branch_watcher

        start_branch_watcher()
        logger.info("[Startup] Branch watcher started")
    except Exception as e:
        logger.error("[Startup] Branch watcher failed to start: %s", e)

    # 无人值守帷幕编排（CU 会话锁屏态代解锁；非桌面端部署零成本空转）。
    try:
        from app.services.locked_use.unattended import start_unattended_curtain_watcher

        start_unattended_curtain_watcher()
        logger.info("[Startup] Unattended curtain watcher started")
    except Exception as e:
        logger.error("[Startup] Unattended curtain watcher failed to start: %s", e)

    try:
        from app.services.agent.goals.usage_limit_resume import get_usage_limit_wake_daemon

        await get_usage_limit_wake_daemon().start()
        logger.info("[Startup] Usage-limit wake daemon started")
    except Exception as e:
        logger.error("[Startup] Usage-limit wake daemon failed to start: %s", e)

    # Hosted only (no-op without a control plane): tells the control plane when to wake this
    # sandbox after the idle recycler pauses it, so parked goals and cron still run on time.
    try:
        from app.services.sandbox_wake import get_wake_schedule_reporter

        await get_wake_schedule_reporter().start()
    except Exception as e:
        logger.error("[Startup] Wake schedule reporter failed to start: %s", e)

    # Initialize per-channel budget guards from persisted policies
    try:
        from app.services.budget.channel_budget import initialize_channel_budgets

        await initialize_channel_budgets()
        logger.info("[Startup] Channel budget guards initialized")
    except Exception as e:
        logger.debug("[Startup] Channel budget init skipped: %s", e)

    # === Phase 3: background work (warmup, housekeeping, route group imports), started once the socket is bound ===
    route_loader = getattr(app_instance.state, "route_loader", None)
    schedule_background_work(route_loader.preload if route_loader is not None else None)

    yield

    # === Shutdown ===
    logger.info("[Shutdown] Application shutting down...")
    await _shutdown(app_instance)
    logger.info("[Shutdown] Application stopped")
