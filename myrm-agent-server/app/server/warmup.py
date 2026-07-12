"""Background warmup tasks after HTTP server is ready.

[INPUT]
- app.lifecycle (POS: 应用生命周期编排)
- app.config.settings (POS: 应用配置)
- app.services.agent.wakeup_handler (POS: 异步子代理唤醒处理器)
- app.services.event.types (POS: 事件系统类型定义)
- app.database.models (POS: ORM 模型定义)
- myrm_agent_harness.utils.text_utils::preheat_tiktoken (POS: Text processing utilities)

[OUTPUT]
- run_async_warmup: 执行后台预热任务（调度器、浏览器池、批量恢复、stale turn 恢复、分词器等）

[POS]
后台预热引擎。HTTP 就绪后在后台异步执行非阻塞预热任务，减少启动延迟。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable

from myrm_agent_harness.utils.runtime.wakeup_registry import set_global_wakeup_handler

from app.config.settings import settings
from app.lifecycle import (
    cleanup_browser_threads,
    init_risk_rules,
    resume_durable_offline_tasks,
    start_approval_ttl_scheduler,
    start_auth_alert_monitor,
    start_auth_log_cleanup_scheduler,
    start_cancellation_cleanup_scheduler,
    start_context_cleanup_scheduler,
    start_context_compaction_telemetry_dispatcher,
    start_db_maintenance_scheduler,
    start_idle_task_listeners,
    start_login_session_cleanup_scheduler,
    start_maintenance_scheduler,
    start_memory_guardian_scheduler,
    start_memory_pressure_monitor,
    start_skill_optimization_listeners,
    warmup_browser_sessions,
    warmup_global_browser_pool,
)
from app.services.agent.evolution.monitor_service import init_evolution_monitor_service
from app.services.agent.wakeup_handler import ServerWakeupHandler

logger = logging.getLogger(__name__)


async def _init_integration_memory() -> None:
    """Initialize IntegrationMemoryService and start the sync daemon."""
    try:
        from myrm_agent_harness.toolkits.context_bundle import ContextBundleFacade
        from myrm_agent_harness.toolkits.memory.graph.sqlite_store import SQLiteGraphStore
        from myrm_agent_harness.toolkits.retriever.embedding.factory import get_embedding_service

        from app.core.retriever.vector.defaults import create_default_vector_store
        from app.services.agent.platform_config import require_platform_embedding_config
        from app.services.memory.integration_memory import (
            IntegrationMemoryService,
            set_integration_memory_service,
        )
        from app.services.memory.integration_sync_daemon import (
            start_integration_sync_daemon,
        )

        vector_store = await create_default_vector_store()
        if vector_store is None:
            logger.info("[Startup] No vector store, skipping IntegrationMemoryService init")
            return

        try:
            emb_config = await require_platform_embedding_config()
        except Exception as exc:
            logger.info(
                "[Startup] WebUI embedding not configured, skipping IntegrationMemoryService init: %s",
                exc,
            )
            return

        facade = ContextBundleFacade.from_state_dir(settings.database.state_dir, ensure_layout=False)
        memory_path = facade.memory_path()

        graph_db_path = memory_path / "integration_graph.db"
        graph_store = SQLiteGraphStore(db_path=str(graph_db_path))

        embedding = get_embedding_service(emb_config)

        svc = IntegrationMemoryService(
            vector_store=vector_store,
            embedding=embedding,
            graph_store=graph_store,
        )
        set_integration_memory_service(svc)
        logger.info("[Startup] IntegrationMemoryService initialized")

        await start_integration_sync_daemon()
    except Exception as exc:
        logger.warning("[Startup] IntegrationMemoryService init failed (non-critical): %s", exc)


async def _start_rate_limiter_cleanup() -> None:
    try:
        from app.core.infra.limiter import limiter

        await limiter.start_cleanup()
        logger.info("[Startup] Rate limiter cleanup task started")
    except Exception as e:
        logger.error("[Startup] Rate limiter cleanup task failed to start: %s", e)
        raise


async def _recover_stale_agent_turns() -> None:
    """Mark agent turns left in pending/running state as interrupted after crash/restart."""
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        return

    from datetime import datetime, timezone

    from sqlalchemy import update

    from app.database.models import AgentTurn
    from app.platform_utils import get_session_factory
    from app.services.event.types import TurnStatus

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            update(AgentTurn)
            .where(AgentTurn.status.in_([TurnStatus.PENDING.value, TurnStatus.RUNNING.value]))
            .values(
                status=TurnStatus.INTERRUPTED.value,
                completed_at=datetime.now(timezone.utc),
            )
        )
        if result.rowcount > 0:
            logger.info(
                "[Startup] Recovered %d stale agent turns → interrupted",
                result.rowcount,
            )
        await session.commit()


async def _recover_incomplete_memory_import_rollbacks() -> None:
    """Resume memory import rollbacks that were journaled before interruption."""

    from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
    from app.platform_utils import get_session_factory
    from app.services.agent.platform_config import require_platform_embedding_config
    from app.services.memory.import_sessions import MemoryImportSessionService

    try:
        embedding_cfg = await require_platform_embedding_config()
    except Exception as exc:
        logger.warning(
            "[Startup] Memory import rollback recovery skipped: %s",
            exc,
        )
        return

    manager = await create_memory_manager(
        resolve_context_binding(
            namespaces=None,
            agent_id=None,
            channel_id=None,
            conversation_id=None,
            task_id=None,
        ),
        embedding_cfg,
        approval_required=False,
    )
    factory = get_session_factory()
    async with factory() as session:
        recovered = await MemoryImportSessionService(session).recover_incomplete_rollbacks(manager)
    if recovered:
        logger.info("[Startup] Recovered %d incomplete memory import rollbacks", recovered)


def _ensure_context_bundle_layout() -> None:
    """Initialize context bundle manifest and scene directories when missing."""

    from app.services.context.context_bundle_service import ContextBundleService

    try:
        report = ContextBundleService().apply_migration()
        if report.manifest_exists:
            logger.info("[Startup] Context bundle manifest ready (bundle_id=%s)", report.bundle_id)
    except Exception as exc:
        logger.warning("[Startup] Context bundle layout init failed: %s", exc)


async def run_async_warmup() -> None:
    """Background warmup tasks after HTTP server is ready.

    These tasks are moved to background to reduce HTTP startup latency.
    Tasks include: schedulers (auth/cleanup/maintenance), browser pool, batch recovery, tokenizer preload, etc.
    """
    warmup_tasks: list[Awaitable[object]] = []

    _ensure_context_bundle_layout()

    await start_memory_pressure_monitor()

    from app.lifecycle.monitors import get_memory_pressure_monitor_instance
    from app.services.agent.gateway import get_agent_gateway

    monitor = get_memory_pressure_monitor_instance()
    if monitor is not None:
        monitor.subscribe(get_agent_gateway())
        logger.info("[Startup] AgentGateway subscribed to MemoryPressureMonitor")

    from app.api.notifications.router import cleanup_old_notifications

    warmup_tasks.extend(
        [
            start_auth_alert_monitor(),
            start_auth_log_cleanup_scheduler(),
            start_context_compaction_telemetry_dispatcher(),
            start_context_cleanup_scheduler(),
            start_db_maintenance_scheduler(),
            start_login_session_cleanup_scheduler(),
            start_maintenance_scheduler(),
            _start_rate_limiter_cleanup(),
            start_skill_optimization_listeners(),
            start_approval_ttl_scheduler(),
            start_cancellation_cleanup_scheduler(),
            start_memory_guardian_scheduler(),
            start_idle_task_listeners(),
            init_evolution_monitor_service(),
            resume_durable_offline_tasks(),
            cleanup_old_notifications(),
        ]
    )

    set_global_wakeup_handler(ServerWakeupHandler())
    logger.info("[Startup] ServerWakeupHandler registered for async subagent completions")

    from myrm_agent_harness.api.hooks import set_global_background_job_finish_handler

    from app.services.agent.background_job_finish_handler import (
        ServerBackgroundJobFinishHandler,
    )

    set_global_background_job_finish_handler(ServerBackgroundJobFinishHandler())
    logger.info("[Startup] ServerBackgroundJobFinishHandler registered for background bash jobs")

    try:
        await warmup_global_browser_pool()
    except Exception as exc:
        logger.error("[Startup] Browser pool initialization failed: %s", exc, exc_info=True)

    # Thread cleanup always runs (zombie detection + old record deletion)
    warmup_tasks.append(cleanup_browser_threads())

    if settings.browser_auto_warmup:
        warmup_tasks.append(warmup_browser_sessions())
    else:
        logger.debug("[Startup] Browser session warmup skipped (browser_auto_warmup=False)")

    try:
        from app.core.media.batch.orchestrator import batch_orchestrator
        from app.platform_utils import get_session_factory

        factory = get_session_factory()

        async def _recover_stale_jobs() -> None:
            async with factory() as session:
                await batch_orchestrator.recover_stale_jobs(session)

        warmup_tasks.append(_recover_stale_jobs())
    except Exception as e:
        logger.warning("Batch job recovery skipped in warmup: %s", e)

    warmup_tasks.append(_recover_stale_agent_turns())
    warmup_tasks.append(_recover_incomplete_memory_import_rollbacks())

    try:
        from myrm_agent_harness.toolkits.retriever.bm25 import preload_tokenizer

        async def _preload_tokenizer() -> None:
            await preload_tokenizer(enable_english_enhancement=False)
            logger.info("Tokenizer preloaded")

        warmup_tasks.append(_preload_tokenizer())
    except Exception as e:
        logger.warning("Tokenizer preload skipped in warmup: %s", e)

    try:
        from myrm_agent_harness.utils.text_utils import preheat_tiktoken

        async def _preheat_tiktoken() -> None:
            await asyncio.to_thread(preheat_tiktoken)

        warmup_tasks.append(_preheat_tiktoken())
    except Exception as e:
        logger.warning("tiktoken preheat skipped in warmup: %s", e)

    warmup_tasks.append(init_risk_rules())

    try:
        from myrm_agent_harness.toolkits.vector import VectorStoreWarmer

        from app.core.retriever.vector import create_default_vector_store

        async def _warmup_vector_store() -> None:
            try:
                store = await create_default_vector_store()
                if store is None:
                    logger.info("[Startup] No vector store configured, skipping vector store warmup")
                    return

                warmer = VectorStoreWarmer(store)
                all_collections = await store.list_collections()
                kb_collections = [(coll, 1536) for coll in all_collections if isinstance(coll, str) and coll.startswith("kb_")]

                if kb_collections:
                    metrics_list = await warmer.warmup_batch_with_verification(kb_collections)
                    for m in metrics_list:
                        if m.success:
                            if m.speedup_ratio and m.verify_duration_ms:
                                logger.info(
                                    f"[Startup] Warmed up collection '{m.collection_name}': "
                                    f"warmup={m.warmup_duration_ms:.2f}ms, "
                                    f"verify={m.verify_duration_ms:.2f}ms, "
                                    f"speedup={m.speedup_ratio:.1f}x"
                                )
                            else:
                                logger.info(
                                    f"[Startup] Warmed up collection '{m.collection_name}' in {m.warmup_duration_ms:.2f}ms"
                                )
                        else:
                            logger.warning(f"[Startup] Failed to warm up collection '{m.collection_name}': {m.error}")
                else:
                    logger.info("[Startup] No vector store collections found, skipping warmup")
            except Exception as e:
                logger.warning(f"[Startup] Vector store warmup failed: {e}")

        warmup_tasks.append(_warmup_vector_store())
    except Exception as e:
        logger.warning("Vector store warmup skipped in warmup: %s", e)

    try:
        from app.lifecycle.task_worker import start_task_worker

        warmup_tasks.append(start_task_worker())
    except Exception as e:
        logger.warning("Task worker startup skipped in warmup: %s", e)

    async def _kanban_gc_warmup() -> None:
        """Run initial kanban GC to clean up data accumulated while offline."""
        try:
            from app.services.kanban.gc import KanbanGCService

            stats = await KanbanGCService().run_gc()
            if stats.events_deleted or stats.runs_deleted or stats.workspaces_deleted:
                logger.info(
                    "[Startup] Kanban GC: %d events, %d runs, %d workspaces cleaned",
                    stats.events_deleted,
                    stats.runs_deleted,
                    stats.workspaces_deleted,
                )
        except Exception as exc:
            logger.warning("[Startup] Kanban GC warmup failed: %s", exc)

    warmup_tasks.append(_kanban_gc_warmup())
    warmup_tasks.append(_init_integration_memory())

    results = await asyncio.gather(*warmup_tasks, return_exceptions=True)

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Warmup task {i} failed: {result}", exc_info=result)

    try:
        from app.core.skills.curator_service import get_stats_collector, start_curator_background_task

        get_stats_collector()  # inject shared collector into harness usage_recorder
        start_curator_background_task()
    except Exception as e:
        logger.warning("[Startup] Curator background task failed to start: %s", e)

    logger.info("[Startup] Warmup completed")
