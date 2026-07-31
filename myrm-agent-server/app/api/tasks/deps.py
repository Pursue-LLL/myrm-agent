"""Task API dependency providers.

[INPUT]
- app.lifecycle.task_worker::get_task_store (POS: SQLiteTaskStore lifecycle entry)

[OUTPUT]
- get_task_store: FastAPI dependency resolving live TaskStore

[POS]
Shared DI helpers for tasks HTTP routes and local E2E fixtures.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.tasks import TaskStore


async def get_task_store() -> TaskStore:
    """Resolve the live SQLite task store from lifecycle."""
    from app.lifecycle.task_worker import get_task_store as get_store

    return get_store()
