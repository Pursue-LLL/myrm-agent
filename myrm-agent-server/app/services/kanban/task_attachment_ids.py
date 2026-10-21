"""Kanban task attachment ID persistence (shared by API routes and attach handler).

[INPUT]
- sqlalchemy KanbanTaskModel.attachment_ids_json (POS: Kanban task row)

[OUTPUT]
- load_task_attachment_ids / save_task_attachment_ids

[POS]
Service-layer attachment ID helpers; API routes and kanban_attach handler must not cross-import app.api.
"""

from __future__ import annotations

from app.core.kanban.adapters.sqlalchemy_mapping import get_attachment_ids, set_attachment_ids


async def load_task_attachment_ids(task_id: str) -> list[str]:
    """Load attachment IDs from the DB for a task."""
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        model = await session.get(KanbanTaskModel, task_id)
        return get_attachment_ids(model) if model else []


async def save_task_attachment_ids(task_id: str, ids: list[str]) -> None:
    """Persist attachment IDs on a task row."""
    from app.database.connection import get_session
    from app.database.models.kanban import KanbanTaskModel

    async with get_session() as session:
        model = await session.get(KanbanTaskModel, task_id)
        if model:
            set_attachment_ids(model, ids)
            await session.commit()
