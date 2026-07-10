"""Application lifespan context manager.

[INPUT]
- app.server.warmup (POS: 后台预热引擎)
- app.server.shutdown (POS: 应用关闭辅助层)
- app.lifecycle (POS: 应用生命周期编排)
- app.config.settings (POS: 应用配置)
- app.database.connection (POS: 数据库连接管理)

[OUTPUT]
- optimized_lifespan: FastAPI lifespan context manager

[POS]
应用生命周期管理器。编排启动三阶段（Critical → Essential → Warmup）和优雅关闭流程。
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from myrm_agent_harness.runtime.startup import StartupTimer

if TYPE_CHECKING:
    from myrm_agent_harness.runtime.context.cleanup_task import ContextCleanupScheduler

from app.config.deploy_mode import is_local_mode
from app.config.settings import settings
from app.core.memory.adapters.setup import shutdown_cached_memory_managers
from app.database.connection import init_database
from app.lifecycle import (
    init_allowlist_store,
    pause_orphaned_active_goals,
    shutdown_global_browser_pool,
    shutdown_skill_optimization_listeners,
    start_channel_gateway,
    start_cron_scheduler,
    start_kanban_dispatchers,
    start_remote_backup_scheduler,
    stop_approval_ttl_scheduler,
    stop_auth_alert_monitor,
    stop_auth_log_cleanup_scheduler,
    stop_cancellation_cleanup_scheduler,
    stop_context_cleanup_scheduler,
    stop_context_compaction_telemetry_dispatcher,
    stop_db_maintenance_scheduler,
    stop_health_history_recorder,
    stop_kanban_dispatchers,
    stop_login_session_cleanup_scheduler,
    stop_memory_guardian_scheduler,
    stop_memory_pressure_monitor,
    stop_remote_backup_scheduler,
)
from app.services.memory.integration_sync_daemon import (
    stop_integration_sync_daemon,
)
from app.server.shutdown import (
    safe_close_checkpointer,
    safe_shutdown_observability,
    safe_stop_cron,
    safe_stop_gateway,
    safe_stop_maintenance_daemon,
    safe_stop_task_worker,
    safe_wait_background_tasks,
    stop_rate_limiter_cleanup,
)
from app.server.warmup import run_async_warmup
from app.services.agent.evolution.monitor_service import (
    shutdown_evolution_monitor_service,
)

logger = logging.getLogger(__name__)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

_checkpointer_cleanup: Callable[[], Awaitable[None]] | None = None
_context_cleanup_scheduler_instance: ContextCleanupScheduler | None = None
_skill_watcher = None


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
            count = await scheduler.dispatch_system_event(
                source="app", event_type="startup", payload={}
            )
            if count:
                logger.info("[Startup] @startup trigger fired %d job(s)", count)
    except Exception as e:
        logger.debug("[Startup] @startup event dispatch skipped: %s", e)


@asynccontextmanager
async def optimized_lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle manager with startup performance optimization.

    Startup phases (optimized for minimal HTTP latency):
        Phase 1a (Critical - Sequential):  Database → Config Migration → Local Admin
        Phase 1b (Critical - Parallel):    Subagent Configs ‖ Code Exec Config ‖ Checkpointer ‖
                                            State Manager ‖ Allowlist Store ‖ Permission Logger ‖
                                            Context Cleanup ‖ Built-in Agents
        Phase 2  (Essential - Parallel):   Channel Gateway ‖ Cron Scheduler ‖ Kanban Dispatchers
        Phase 3  (Warmup - Async):         Schedulers ‖ Browser Pool ‖ Batch Recovery ‖
                                            Tokenizer ‖ Risk Rules ‖ Vector Cache (background)

    Shutdown: Storage → (Schedulers ‖ Cron ‖ Channel Gateway ‖ Browser Pool ‖ Checkpointer)
    """
    global _checkpointer_cleanup, _context_cleanup_scheduler_instance, _skill_watcher

    print(f"🐍 Python {sys.version.split()[0]}")

    from myrm_agent_harness.infra.tls_compat import apply_global_tls_relaxation

    if apply_global_tls_relaxation():
        logger.info("[Startup] Enterprise TLS compatibility enabled (MYRM_TLS_STRICT=0)")

    timer = StartupTimer()
    logger.info("[Startup] Application starting...")

    from app.platform_utils.deployment_capabilities import get_deployment_capabilities

    if get_deployment_capabilities().runs_sandbox_startup_validation:
        settings.validate_for_sandbox()

    # === Phase 1: Critical tasks ===
    async with timer.phase("critical"):
        await _phase_1a_sequential()
        await _phase_1b_parallel()

    # === Phase 1.5: Observability setup ===
    async with timer.phase("monitoring"):
        from app.core.monitoring import setup_monitoring

        setup_monitoring(app_instance)

    # === Phase 2: Essential services ===
    async with timer.phase("core"):
        from app.services.background.daemon import maintenance_daemon

        await maintenance_daemon.start()

        gw_result, cron_result, kanban_result, backup_result = await asyncio.gather(
            start_channel_gateway(),
            start_cron_scheduler(),
            start_kanban_dispatchers(),
            start_remote_backup_scheduler(),
            return_exceptions=True,
        )

        if isinstance(gw_result, Exception):
            logger.error("[Startup] Channel Gateway failed to start: %s", gw_result)
        if isinstance(cron_result, Exception):
            logger.error("[Startup] Cron scheduler failed to start: %s", cron_result)
        if isinstance(kanban_result, Exception):
            logger.error("[Startup] Kanban dispatchers failed to start: %s", kanban_result)
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

    logger.info(f"[Startup] HTTP server ready: {timer.metrics.to_dict()}")

    # === Phase 3: Async warmup (background, non-blocking) ===
    logger.info("[Startup] Starting background warmup...")
    asyncio.create_task(run_async_warmup())

    try:
        from app.services.agent.goal_registry import GoalRegistry

        GoalRegistry.start_branch_watcher()
        logger.info("[Startup] Branch watcher started")
    except Exception as e:
        logger.error("[Startup] Branch watcher failed to start: %s", e)

    asyncio.create_task(pause_orphaned_active_goals())

    # Dispatch @startup system event for trigger-based cron jobs
    asyncio.create_task(_dispatch_startup_event())

    # Initialize per-channel budget guards from persisted policies
    try:
        from app.services.budget.channel_budget import initialize_channel_budgets

        await initialize_channel_budgets()
        logger.info("[Startup] Channel budget guards initialized")
    except Exception as e:
        logger.debug("[Startup] Channel budget init skipped: %s", e)

    yield

    # === Shutdown ===
    logger.info("[Shutdown] Application shutting down...")
    await _shutdown(app_instance)
    logger.info("[Shutdown] Application stopped")


async def _phase_1a_sequential() -> None:
    """Phase 1a: Sequential critical tasks (DB + dependent tasks)."""
    try:
        await init_database()
        logger.info("[Startup] Database initialized")
    except Exception as e:
        logger.error("[Startup] Database initialization failed: %s", e)

        from app.config.settings import settings
        from app.database.recovery import rescue_database
        from app.platform_utils import reset_database_engine
        from app.server.status import system_status

        db_path = settings.database.sqlite_path

        # 1. Try .iterdump rescue (last-resort row-level data salvage)
        if rescue_database(db_path):
            system_status.database_recovered = True
            await reset_database_engine()
            await init_database()
            logger.info("[Startup] Database rescued successfully")
        else:
            # 2. Try multi-snapshot integrity-verified restore
            restored = False
            try:
                from app.database.backup import get_sqlite_backup_manager

                manager = get_sqlite_backup_manager()
                if manager is not None:
                    result = manager.restore_latest()
                    if result.restored:
                        restored = True
                        system_status.database_recovered = True
                        await reset_database_engine()
                        await init_database()
                        logger.info("[Startup] Database restored from snapshot %s", result.snapshot_file)
            except Exception as restore_exc:
                logger.warning("[Startup] Snapshot restore failed: %s", restore_exc)

            # 3. Degrade to in-memory as ultimate fallback
            if not restored:
                logger.warning("[Startup] All recovery methods exhausted, degrading to in-memory mode")
                system_status.database_degraded = True
                settings.database.sqlite_path = ":memory:"
                await reset_database_engine()
                await init_database()

    try:
        from app.platform_utils.sandbox.saas_providers_seed import seed_saas_platform_providers_if_needed

        await seed_saas_platform_providers_if_needed()
    except Exception as exc:
        logger.warning("[Startup] SaaS provider seed skipped: %s", exc)

    await _register_db_pool_metrics_task()

    try:
        from myrm_agent_harness.core.features import init_features

        from app.services.features.feature_config_service import load_user_overrides
        from app.services.features.registration import register_all_features

        register_all_features()
        user_overrides = load_user_overrides()
        feature_set = init_features(overrides=user_overrides)
        logger.info(
            "[Startup] Feature flags initialized (%d enabled)",
            len(feature_set.enabled_features()),
        )
    except Exception as e:
        logger.error("[Startup] Feature flags initialization failed: %s", e)
        raise

    if is_local_mode():
        try:
            from app.database.connection import get_session
            from app.services.config.migration import migrate_configs_to_encrypted

            async with get_session() as db:
                stats = await migrate_configs_to_encrypted(db)
                if stats["migrated"] > 0:
                    logger.info(f"[Startup] Config encryption migration complete: {stats}")
                else:
                    logger.debug(f"[Startup] No configs to migrate: {stats}")
        except Exception as e:
            logger.warning("[Startup] Config encryption migration failed (non-critical): %s", e)

    try:
        from app.services.config.key_consolidation import consolidate_split_providers_keys

        stats = await consolidate_split_providers_keys()
        if stats.get("merged") or stats.get("deleted"):
            logger.info("[Startup] Providers key consolidation complete: %s", stats)
    except Exception as e:
        logger.warning("[Startup] Providers key consolidation failed (non-critical): %s", e)

    try:
        from app.core.infra.tls_config import apply_tls_config_from_db

        await apply_tls_config_from_db()
    except Exception as e:
        logger.debug("[Startup] TLS config from DB skipped: %s", e)


async def _phase_1b_parallel() -> None:
    """Phase 1b: Parallel independent tasks after DB ready."""
    global _checkpointer_cleanup, _context_cleanup_scheduler_instance, _skill_watcher

    async def _init_subagent_configs() -> None:
        from app.ai_agents.subagent_presets import register_default_subagent_configs

        register_default_subagent_configs()

    async def _init_code_execution_config() -> None:
        _apply_code_execution_config()

    async def _init_checkpointer_task() -> None:
        global _checkpointer_cleanup
        from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer

        from app.config.deploy_mode import get_deploy_mode
        from app.config.settings import settings
        from app.platform_utils import set_checkpointer

        checkpointer, _checkpointer_cleanup = await create_checkpointer(
            mode=settings.database.checkpointer_mode,
            sqlite_db_path=settings.database.sqlite_db_path,
            deploy_mode=get_deploy_mode().value,
        )
        set_checkpointer(checkpointer)
        logger.info("[Startup] Checkpointer initialized")

    async def _init_state_manager_task() -> None:
        from app.core.skills.state_manager_instance import init_state_manager

        init_state_manager(base_dir=".myrm/skills")
        logger.info("[Startup] SkillStateManager initialized")

    async def _init_skill_watcher_task() -> None:
        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        if not get_deployment_capabilities().is_sandbox_instance:
            from pathlib import Path

            from myrm_agent_harness.backends.skills.watcher import SkillWatcher

            from app.config.settings import settings

            # Watch the user's local skills directory
            local_skills_dir = Path(settings.database.state_dir) / "skills"
            local_skills_dir.mkdir(parents=True, exist_ok=True)

            global _skill_watcher
            _skill_watcher = SkillWatcher(local_skills_dir)
            _skill_watcher.start()
            logger.info("[Startup] SkillWatcher initialized for local development")

    async def _init_allowlist_store_task() -> None:
        await init_allowlist_store()
        logger.info("[Startup] Allowlist store initialized")

    async def _init_permission_logger_task() -> None:
        from app.core.skills.permission_logger import start_permission_logger

        start_permission_logger()
        logger.info("[Startup] Skill permission logger started")

    async def _init_context_cleanup_task() -> None:
        global _context_cleanup_scheduler_instance
        from pathlib import Path

        from myrm_agent_harness.runtime.context.cleanup_task import (
            ContextCleanupScheduler,
        )
        from myrm_agent_harness.toolkits.code_execution import create_workspace_service

        workspace_svc = create_workspace_service(root_dir=Path(settings.database.harness_dir))
        sandboxes_root = workspace_svc.workspaces_root

        if sandboxes_root.exists():
            scheduler = ContextCleanupScheduler(sandboxes_root, interval_hours=24)
            scheduler.start()
            _context_cleanup_scheduler_instance = scheduler
            logger.info("[Startup] Context cleanup task started (root: %s)", sandboxes_root)
        else:
            logger.debug(
                "[Startup] Sandboxes root not found, skip cleanup task: %s",
                sandboxes_root,
            )

    async def _init_optimization_scheduler_task() -> None:
        from app.core.infra.server_globals import set_optimization_scheduler
        from app.services.skill_optimization.scheduler_factory import (
            create_optimization_scheduler,
        )

        optimization_scheduler = await create_optimization_scheduler()
        if optimization_scheduler:
            set_optimization_scheduler(optimization_scheduler)
            await optimization_scheduler.start_monitoring()
            logger.info("[Startup] OptimizationScheduler initialized and worker started successfully")
        else:
            logger.warning("[Startup] OptimizationScheduler initialization skipped (dependencies missing)")

    async def _init_idle_handlers_task() -> None:
        from app.core.infra.idle_handlers import register_all_idle_handlers

        register_all_idle_handlers()

    async def _init_prebuilt_skills() -> None:
        from myrm_agent_harness.toolkits.storage.factory import get_storage_provider

        from app.core.skills.prebuilt_sync import sync_prebuilt_seeds
        from app.core.skills.store.service import skills_service

        storage = get_storage_provider()
        sync_result = await sync_prebuilt_seeds(storage)
        if sync_result.skill_ids:
            await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))

    async def _init_builtin_agents() -> None:
        from app.services.agent.builtin_initializer import initialize_builtin_agents

        await initialize_builtin_agents()

    async def _init_harness_bridge_task() -> None:
        from app.lifecycle.harness_bridge import setup_harness_bridge

        setup_harness_bridge()

    async def _init_security_reviewer_task() -> None:
        from myrm_agent_harness.agent.middlewares.approval.batch_processor import (
            register_security_reviewer,
        )

        from app.core.security.llm_reviewer import DynamicLLMSecurityReviewer

        try:
            reviewer = DynamicLLMSecurityReviewer(timeout_seconds=3.0)
            register_security_reviewer(reviewer)
            logger.info("[Startup] DynamicLLMSecurityReviewer initialized and registered")
        except Exception as e:
            logger.warning("[Startup] Failed to initialize DynamicLLMSecurityReviewer: %s", e)

    async def _init_vault_credentials_task() -> None:
        from app.services.security.vault_credential_service import VaultCredentialService

        try:
            service = VaultCredentialService()
            await service.sync_all_to_vault()
        except Exception as e:
            logger.error("[Startup] Failed to sync Vault Credentials: %s", e)

    async def _init_wiki_vault_task() -> None:
        from app.services.wiki.vault_service import init_wiki_vault_at_startup

        await init_wiki_vault_at_startup()

    results = await asyncio.gather(
        _init_subagent_configs(),
        _init_code_execution_config(),
        _init_checkpointer_task(),
        _init_state_manager_task(),
        _init_skill_watcher_task(),
        _init_allowlist_store_task(),
        _init_permission_logger_task(),
        _init_context_cleanup_task(),
        _init_optimization_scheduler_task(),
        _init_idle_handlers_task(),
        _init_prebuilt_skills(),
        _init_builtin_agents(),
        _init_harness_bridge_task(),
        _init_security_reviewer_task(),
        _init_vault_credentials_task(),
        _init_wiki_vault_task(),
        return_exceptions=True,
    )

    _labels = [
        "Subagent configs",
        "Code execution config",
        "Checkpointer",
        "State manager",
        "Skill watcher",
        "Allowlist store",
        "Permission logger",
        "Context cleanup",
        "Optimization scheduler",
        "Idle handlers",
        "Prebuilt skills",
        "Built-in agents",
        "Harness event bridge",
        "Security reviewer",
        "Vault credentials",
        "Wiki vault",
    ]
    for label, result in zip(_labels, results, strict=True):
        if isinstance(result, Exception):
            logger.error("[Startup] %s initialization failed: %s", label, result)


async def _shutdown(app_instance: FastAPI) -> None:
    """Graceful shutdown: stop all components in parallel."""
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

    try:
        from app.core.storage.lifecycle import shutdown_all_storages

        await shutdown_all_storages(timeout=60.0, force=False)
        logger.info("[Shutdown] Storage instances closed")
    except Exception as e:
        logger.error("[Shutdown] Storage shutdown failed: %s", e)

    if _context_cleanup_scheduler_instance is not None:
        try:
            await _context_cleanup_scheduler_instance.stop()
        except Exception as e:
            logger.error("[Shutdown] Context cleanup task stop failed: %s", e)

    if _skill_watcher is not None:
        try:
            _skill_watcher.stop()
            logger.info("[Shutdown] SkillWatcher stopped")
        except Exception as e:
            logger.error("[Shutdown] SkillWatcher stop failed: %s", e)

    try:
        from app.services.agent.goal_registry import GoalRegistry

        GoalRegistry.stop_branch_watcher()
    except Exception as e:
        logger.error("[Shutdown] Branch watcher stop failed: %s", e)

    try:
        from app.core.skills.curator_service import stop_curator_background_task

        stop_curator_background_task()
    except Exception as e:
        logger.error("[Shutdown] Curator background task stop failed: %s", e)

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

    shutdown_results = await asyncio.gather(
        safe_stop_cron(),
        safe_stop_gateway(),
        stop_kanban_dispatchers(),
        shutdown_global_browser_pool(),
        safe_close_checkpointer(_checkpointer_cleanup),
        stop_auth_alert_monitor(),
        stop_auth_log_cleanup_scheduler(),
        stop_context_compaction_telemetry_dispatcher(),
        stop_context_cleanup_scheduler(),
        stop_db_maintenance_scheduler(),
        stop_health_history_recorder(),
        stop_login_session_cleanup_scheduler(),
        stop_approval_ttl_scheduler(),
        stop_cancellation_cleanup_scheduler(),
        stop_memory_guardian_scheduler(),
        shutdown_cached_memory_managers(),
        stop_memory_pressure_monitor(),
        stop_remote_backup_scheduler(),
        safe_stop_task_worker(),
        safe_stop_maintenance_daemon(),
        stop_rate_limiter_cleanup(),
        safe_wait_background_tasks(),
        safe_shutdown_observability(),
        shutdown_skill_optimization_listeners(),
        shutdown_evolution_monitor_service(),
        stop_integration_sync_daemon(),
        harness_bridge_task,
        _shutdown_mcp(),
        return_exceptions=True,
    )
    for r in shutdown_results:
        if isinstance(r, Exception):
            logger.error("[Shutdown] Component stop failed: %s", r)

    # Final: WAL checkpoint + engine dispose to ensure all data is flushed to disk
    try:
        from app.config.settings import settings
        from app.platform_utils import get_database_engine

        engine = get_database_engine()
        try:
            async with engine.begin() as conn:
                await conn.exec_driver_sql("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception as e:
            logger.warning("[Shutdown] Database WAL checkpoint failed (ignoring): %s", e)
        await engine.dispose()
        logger.info("[Shutdown] Database engine disposed")

        from app.database.backup import get_sqlite_backup_manager

        manager = get_sqlite_backup_manager()
        if manager is not None:
            manager.create_backup()
    except Exception as e:
        logger.error("[Shutdown] Database backup failed: %s", e)


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
