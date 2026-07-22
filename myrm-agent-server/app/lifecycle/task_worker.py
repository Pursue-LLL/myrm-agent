"""Task worker lifecycle management.

[INPUT]
- app.config.settings::settings (POS: 全局配置)
- app.tasks::ImageTaskExecutor, TaskWorker (POS: 后台任务执行器)
- app.tasks.events::task_event_bus (POS: 任务状态事件总线)

[OUTPUT]
- start_task_worker / stop_task_worker: 异步任务 worker 启停
- get_task_store: API 依赖注入用 SQLite 任务存储

[POS]
运行时后台任务 worker 生命周期编排（含 Vault GC 定时清理）。
"""

import logging
from pathlib import Path
from typing import cast

from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore

from app.config.settings import settings
from app.tasks import ImageTaskExecutor, TaskWorker, VideoTaskExecutor
from app.tasks.worker import _TaskExecutor

logger = logging.getLogger(__name__)

_task_worker_instance: TaskWorker | None = None
_task_store_instance: SQLiteTaskStore | None = None


def get_task_store() -> SQLiteTaskStore:
    """Get task store instance (for API dependency injection)."""
    if _task_store_instance is None:
        msg = "Task store not initialized. Call start_task_worker() first."
        raise RuntimeError(msg)
    return _task_store_instance


async def _start_vault_gc() -> None:
    """Background task to periodically clean up expired vault objects (>7 days)."""
    import asyncio
    import time

    from myrm_agent_harness.core.artifacts.paths import resolve_workspace_artifact_vault_dir

    ws_root = getattr(settings, "workspace_root", None)
    workspace_root = Path(ws_root) if ws_root else Path.cwd()
    vault_dir = resolve_workspace_artifact_vault_dir(workspace_root)

    gc_interval_seconds = 3600
    expire_seconds = 7 * 24 * 3600

    while True:
        try:
            if vault_dir.exists():
                now = time.time()
                deleted_count = 0
                for f in vault_dir.glob("**/*"):
                    if f.is_file():
                        try:
                            if now - f.stat().st_mtime > expire_seconds:
                                f.unlink()
                                deleted_count += 1
                        except Exception as inner_e:
                            logger.debug("Failed to delete expired vault file %s: %s", f, inner_e)
                if deleted_count > 0:
                    logger.info("Vault GC completed: Deleted %d expired files from %s", deleted_count, vault_dir)
        except Exception as e:
            logger.error("Vault GC task encountered an error: %s", e)

        await asyncio.sleep(gc_interval_seconds)


async def start_task_worker() -> TaskWorker:
    """Start task worker for async task execution."""
    global _task_worker_instance, _task_store_instance

    try:
        store_path = Path(settings.database.state_dir) / "tasks.db"
        store = SQLiteTaskStore(db_path=str(store_path))
        await store.initialize()
        _task_store_instance = store

        from app.tasks.image_config_resolver import resolve_image_generation_config
        from app.tasks.video_config_resolver import resolve_video_generation_config

        executors: list[_TaskExecutor] = cast(
            list[_TaskExecutor],
            [
                ImageTaskExecutor(resolve_image_generation_config),
                VideoTaskExecutor(resolve_video_generation_config),
            ],
        )

        from app.tasks.events import task_event_bus

        worker = TaskWorker(
            store=store,
            executors=executors,
            max_concurrency=3,
            worker_id="worker-1",
            on_status_change=task_event_bus.emit,
        )

        import asyncio

        asyncio.create_task(worker.start())
        asyncio.create_task(_start_vault_gc())

        _task_worker_instance = worker
        logger.info("[Startup] Task worker started")
        return worker

    except Exception as e:
        logger.error(f"[Startup] Task worker failed to start: {e}", exc_info=True)
        raise


async def stop_task_worker() -> None:
    """Stop task worker gracefully."""
    global _task_worker_instance

    if _task_worker_instance:
        try:
            await _task_worker_instance.stop()
            logger.info("[Shutdown] Task worker stopped")
        except Exception as e:
            logger.error(f"[Shutdown] Task worker stop failed: {e}", exc_info=True)


__all__ = ["start_task_worker", "stop_task_worker", "get_task_store"]
