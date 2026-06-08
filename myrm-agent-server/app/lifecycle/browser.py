"""Browser lifecycle management — pool warmup, thread cleanup, session recovery."""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


async def warmup_global_browser_pool() -> None:
    """预热全局浏览器池（预创建 Browser 实例和 Page）"""
    from myrm_agent_harness.toolkits.browser.pool import get_global_browser_pool
    from myrm_agent_harness.toolkits.web_fetch import web_fetch_tools

    from app.config.browser import get_browser_launch_options, get_browser_pool_config
    from app.config.settings import settings
    from app.core.security.browser_vault import get_global_session_vault

    # Inject global SessionVault into web_fetch_tools
    web_fetch_tools.set_session_vault(get_global_session_vault())

    config = get_browser_pool_config()
    launch_options = get_browser_launch_options()
    pool = get_global_browser_pool(
        max_browsers=settings.browser_pool.max_browsers,
        config=config,
        launch_options=launch_options,
    )
    await pool.warmup(
        browsers=settings.browser_pool.warmup_browsers,
        pages_per_context=settings.browser_pool.warmup_pages,
    )
    logger.info("GlobalBrowserPool warmup completed")


async def shutdown_global_browser_pool() -> None:
    """关闭全局浏览器池"""
    from myrm_agent_harness.toolkits.browser.pool import get_global_browser_pool

    pool = get_global_browser_pool()
    await pool.shutdown()
    logger.info("[Shutdown] GlobalBrowserPool closed")


async def cleanup_browser_threads() -> None:
    """清理僵尸线程和过期记录。

    独立于浏览器预热，确保无论 browser_auto_warmup 设置如何，
    僵尸线程检测和旧记录清理始终在启动时和周期性维护中执行。

    清理策略：
    1. 将超过 48 小时未活跃的 active 线程标记为 failed（僵尸线程）
    2. 删除超过 7 天的已完成/失败记录
    """
    try:
        from datetime import datetime, timedelta

        from app.platform_utils import get_checkpointer

        checkpointer = get_checkpointer()

        if not hasattr(checkpointer, "thread_store"):
            logger.debug("Checkpointer does not support thread registry, skip cleanup")
            return

        from myrm_agent_harness.toolkits.browser.checkpoint import ThreadStore

        thread_store: ThreadStore = checkpointer.thread_store

        stale_threshold = datetime.now() - timedelta(hours=48)
        active_threads = await thread_store.find_active_threads(max_age_hours=None)

        zombie_count = 0
        for record in active_threads:
            if record.last_active_at < stale_threshold:
                await thread_store.mark_failed(record.thread_id)
                zombie_count += 1
                logger.info(
                    "Cleanup: marked zombie thread %s as failed (inactive since %s)",
                    record.thread_id,
                    record.last_active_at.isoformat(),
                )

        old_records_removed = await thread_store.cleanup_old_records(max_age_days=7.0)

        logger.info(
            "Thread cleanup: %d zombie threads marked failed, %d old records deleted",
            zombie_count,
            old_records_removed,
        )

    except Exception as exc:
        logger.error("Thread cleanup failed: %s", exc, exc_info=True)


async def warmup_browser_sessions() -> None:
    """预热活跃浏览器会话（保持登录状态）。

    仅预热 24 小时内活跃的线程。需要 browser_auto_warmup=True。
    """
    try:
        from datetime import datetime, timedelta

        from app.platform_utils import get_checkpointer

        checkpointer = get_checkpointer()

        if not hasattr(checkpointer, "thread_store"):
            return

        from myrm_agent_harness.toolkits.browser.checkpoint import ThreadStore

        thread_store: ThreadStore = checkpointer.thread_store

        stale_threshold = datetime.now() - timedelta(hours=48)
        active_threads = await thread_store.find_active_threads(max_age_hours=None)

        warmup_candidates = [
            record
            for record in active_threads
            if record.last_active_at >= stale_threshold and (datetime.now() - record.last_active_at).total_seconds() < 86400
        ]

        if not warmup_candidates:
            return

        logger.info("Found %d threads eligible for session warmup (within 24h)", len(warmup_candidates))

        from myrm_agent_harness.toolkits.browser.checkpoint import ParallelRecoveryOrchestrator
        from myrm_agent_harness.toolkits.browser.pool import get_global_browser_pool

        from app.core.security.browser_vault import get_global_session_vault

        session_vault = get_global_session_vault()
        browser_pool = get_global_browser_pool()

        orchestrator = ParallelRecoveryOrchestrator(
            checkpointer=checkpointer,
            thread_store=thread_store,
            browser_pool=browser_pool,
            session_vault=session_vault,
            max_concurrent_recoveries=3,
        )

        await orchestrator.initialize()

        warmup_start = time.perf_counter()
        result = await orchestrator.recover_all(max_age_hours=24.0)
        warmup_elapsed_ms = (time.perf_counter() - warmup_start) * 1000

        logger.info(
            "Browser session warmup: %d/%d sessions recovered in %.1fms",
            result["success_count"],
            result["total_count"],
            warmup_elapsed_ms,
        )

        if result["failure_count"] > 0:
            logger.warning("Warmup failures: %s", result["failed_threads"])

    except Exception as warmup_exc:
        logger.error("Browser session warmup failed: %s", warmup_exc, exc_info=True)


async def cleanup_and_warmup_browser_threads() -> None:
    """Combined cleanup + warmup (backward compatibility entry point)."""
    await cleanup_browser_threads()
    await warmup_browser_sessions()
