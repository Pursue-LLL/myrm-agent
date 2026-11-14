"""Task API dependency providers.

[INPUT]
- app.lifecycle.task_worker::ensure_task_store, get_task_worker (POS: SQLiteTaskStore / TaskWorker lifecycle entry)

[OUTPUT]
- get_task_store: FastAPI dependency resolving the TaskStore, opened on first use (usable before the worker starts)
- get_task_worker: FastAPI dependency resolving the running TaskWorker (None when not started)

[POS]
Shared DI helpers for tasks HTTP routes and local E2E fixtures.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.tasks import TaskStore

if TYPE_CHECKING:
    from app.tasks.worker import TaskWorker


async def get_task_store() -> TaskStore:
    """Resolve the SQLite task store; the API serves from the first request on, before the worker has started."""
    from app.lifecycle.task_worker import ensure_task_store

    return await ensure_task_store()


async def get_task_worker() -> "TaskWorker | None":
    """Resolve the running worker so a cancel can also stop the in-flight execution."""
    from app.lifecycle.task_worker import get_task_worker as get_worker

    return get_worker()
