"""Task API dependency providers.

[INPUT]
- app.lifecycle.task_worker::get_task_store, get_task_worker (POS: SQLiteTaskStore / TaskWorker lifecycle entry)

[OUTPUT]
- get_task_store: FastAPI dependency resolving live TaskStore
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
    """Resolve the live SQLite task store from lifecycle."""
    from app.lifecycle.task_worker import get_task_store as get_store

    return get_store()


async def get_task_worker() -> "TaskWorker | None":
    """Resolve the running worker so a cancel can also stop the in-flight execution."""
    from app.lifecycle.task_worker import get_task_worker as get_worker

    return get_worker()
