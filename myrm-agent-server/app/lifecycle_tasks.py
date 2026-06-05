"""Task worker lifecycle management."""

import logging
from pathlib import Path
from typing import cast

from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore

from app.config.settings import settings
from app.tasks import ImageTaskExecutor, TaskWorker
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
    from pathlib import Path

    # Check if vault directory exists
    ws_root = getattr(settings, "workspace_root", None)
    workspace_root = Path(ws_root) if ws_root else Path.cwd()
    vault_dir = workspace_root / ".myrm" / "vault"

    gc_interval_seconds = 3600  # Check every hour
    expire_seconds = 7 * 24 * 3600  # 7 days

    while True:
        try:
            if vault_dir.exists():
                now = time.time()
                deleted_count = 0
                for f in vault_dir.glob("**/*"):
                    if f.is_file():
                        try:
                            # Use mtime to check age
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
        # Initialize SQLite task store
        store_path = Path(settings.database.state_dir) / "tasks.db"
        store = SQLiteTaskStore(db_path=str(store_path))
        await store.initialize()
        _task_store_instance = store

        # Create image generator
        from myrm_agent_harness.toolkits.llms.image import ImageGenerationConfig, ImageGenerator

        image_config = ImageGenerationConfig(model="dall-e-3")
        image_generator = ImageGenerator(config=image_config)

        # Create executors (cast: list invariance vs structural _TaskExecutor protocol)
        executors: list[_TaskExecutor] = cast(
            list[_TaskExecutor],
            [
                ImageTaskExecutor(image_generator),
            ],
        )

        # Create worker with event bus integration
        from app.tasks.events import task_event_bus

        worker = TaskWorker(
            store=store,
            executors=executors,
            max_concurrency=3,
            worker_id="worker-1",
            on_status_change=task_event_bus.emit,
        )

        # Start worker in background
        import asyncio

        asyncio.create_task(worker.start())

        # Start Vault GC
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
