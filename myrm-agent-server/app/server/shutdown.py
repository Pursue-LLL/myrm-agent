"""Application shutdown helpers.

[INPUT]
- app.lifecycle (POS: 应用生命周期编排)
- app.core.channel_bridge.setup (POS: Channel Gateway 启动/停止)
- app.core.cron.adapters.setup (POS: Cron Scheduler 管理)

[OUTPUT]
- stop_rate_limiter_cleanup: 停止限流器清理
- safe_stop_cron: 安全停止 Cron Scheduler
- safe_stop_gateway: 安全停止 Channel Gateway
- safe_stop_task_worker: 安全停止任务 Worker
- safe_close_checkpointer: 安全关闭 Checkpointer
- safe_stop_maintenance_daemon: 安全停止维护守护进程
- safe_wait_background_tasks: 等待 Harness 后台任务完成
- safe_shutdown_observability: 安全关闭 OpenTelemetry

[POS]
应用关闭辅助层。提供各组件的安全关闭函数，所有函数捕获异常不抛出，确保 shutdown 流程不中断。
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


async def stop_rate_limiter_cleanup() -> None:
    try:
        from app.core.infra.limiter import limiter

        await limiter.stop_cleanup()
        logger.info("[Shutdown] Rate limiter cleanup task stopped")
    except Exception as e:
        logger.error("[Shutdown] Rate limiter cleanup task stop failed: %s", e)


async def safe_stop_cron() -> None:
    from app.core.cron.adapters.setup import get_cron_scheduler

    await get_cron_scheduler().stop()
    logger.info("Cron scheduler stopped")


async def safe_stop_gateway() -> None:
    from app.core.channel_bridge.setup import stop_channel_gateway

    await stop_channel_gateway()


async def safe_stop_task_worker() -> None:
    from app.lifecycle_tasks import stop_task_worker

    await stop_task_worker()
    logger.info("Task worker stopped")


async def safe_close_checkpointer(cleanup_fn: Callable[[], Awaitable[None]] | None) -> None:
    if cleanup_fn is not None:
        await cleanup_fn()


async def safe_stop_maintenance_daemon() -> None:
    from app.services.background.daemon import maintenance_daemon

    await maintenance_daemon.stop(timeout_seconds=5.0)


async def safe_wait_background_tasks() -> None:
    """Wait for Harness background tasks (skill review, memory extraction) to complete."""
    try:
        from myrm_agent_harness.agent.skill_agent import wait_all_background_tasks

        await wait_all_background_tasks(timeout_seconds=30.0)
        logger.info("[Shutdown] Harness background tasks waited")
    except Exception as e:
        logger.warning("[Shutdown] Harness background tasks wait failed: %s", e)


async def safe_shutdown_observability() -> None:
    """Gracefully shutdown OpenTelemetry tracing and metrics providers."""
    try:
        from myrm_agent_harness.infra.tracing import shutdown_metrics, shutdown_tracing

        shutdown_tracing()
        shutdown_metrics()
        logger.info("[Shutdown] Observability providers shutdown complete")
    except Exception as e:
        logger.warning("[Shutdown] Observability shutdown failed: %s", e)
