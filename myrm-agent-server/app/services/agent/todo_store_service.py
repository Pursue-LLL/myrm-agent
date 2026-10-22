"""
[POS] app/services/agent/todo_store_service.py
[INPUT] threading, pathlib, typing, myrm_agent_harness.agent.sub_agents.todo_store, app.schemas.todo_store
[OUTPUT] TodoStoreService, get_todo_store_service

Service layer managing session-scoped shared Todo plan stores and safe HUD projections.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import cast

from myrm_agent_harness.agent.sub_agents.todo_store import (
    SharedTodoHudReader,
    SharedTodoStore,
    TodoItem,
    TodoItemStatus,
)

from app.schemas.todo_store import (
    CreateTodoItemRequestDTO,
    TodoHudProjectionDTO,
    TodoItemDTO,
    TodoItemStatusLiteral,
    TodoListResponseDTO,
    UpdateTodoItemRequestDTO,
)


def _to_dto(item: TodoItem) -> TodoItemDTO:
    """Convert harness TodoItem to DTO."""
    return TodoItemDTO(
        item_id=item.item_id,
        title=item.title,
        description=item.description,
        status=cast(TodoItemStatusLiteral, item.status),
        assignee=item.assignee,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


class TodoStoreService:
    """Session-scoped shared Todo store coordinator for multi-agent workflows."""

    def __init__(self, base_storage_dir: Path | None = None) -> None:
        self._base_storage_dir = base_storage_dir
        self._lock = threading.Lock()
        self._stores: dict[str, SharedTodoStore] = {}

    def get_store(self, session_id: str) -> SharedTodoStore:
        """Get or initialize thread-safe store for a specific session."""
        with self._lock:
            if session_id not in self._stores:
                storage_path: Path | None = None
                if self._base_storage_dir is not None:
                    storage_path = self._base_storage_dir / session_id / "todo.json"
                self._stores[session_id] = SharedTodoStore(
                    session_id=session_id,
                    storage_path=storage_path,
                )
            return self._stores[session_id]

    def add_item(self, session_id: str, req: CreateTodoItemRequestDTO) -> TodoItemDTO:
        """Declare a new plan item in session's shared Todo store."""
        store = self.get_store(session_id)
        item = store.add_item(
            title=req.title,
            description=req.description,
            assignee=req.assignee,
            item_id=req.item_id or "",
        )
        return _to_dto(item)

    def update_item(
        self,
        session_id: str,
        item_id: str,
        req: UpdateTodoItemRequestDTO,
    ) -> TodoItemDTO:
        """Update existing plan item fields."""
        store = self.get_store(session_id)
        stat_val = cast(TodoItemStatus, req.status) if req.status else None
        item = store.update_item(
            item_id=item_id,
            title=req.title,
            description=req.description,
            status=stat_val,
            assignee=req.assignee,
        )
        return _to_dto(item)

    def remove_item(self, session_id: str, item_id: str) -> bool:
        """Remove a plan item from session store."""
        store = self.get_store(session_id)
        return store.remove_item(item_id)

    def clear_items(self, session_id: str) -> None:
        """Clear all plan items in session."""
        store = self.get_store(session_id)
        store.clear()

    def list_items(self, session_id: str) -> TodoListResponseDTO:
        """List all plan items in session."""
        store = self.get_store(session_id)
        state = store.get_state()
        dtos = [_to_dto(i) for i in state.items]
        return TodoListResponseDTO(
            session_id=session_id,
            items=dtos,
            total_count=len(dtos),
            semantic_contract=state.semantic_contract,
        )

    def get_hud_projection(self, session_id: str) -> TodoHudProjectionDTO:
        """Generate sanitized read-only HUD projection for session."""
        store = self.get_store(session_id)
        reader = SharedTodoHudReader(store)
        proj = reader.project_hud()
        return TodoHudProjectionDTO(
            session_id=session_id,
            total_count=proj.total_count,
            pending_count=proj.pending_count,
            in_progress_count=proj.in_progress_count,
            completed_count=proj.completed_count,
            cancelled_count=proj.cancelled_count,
            progress_pct=proj.progress_pct,
            active_items=[_to_dto(i) for i in proj.active_items],
            formatted_hud_lines=proj.formatted_hud_lines,
            semantic_contract=proj.semantic_contract,
        )


_GLOBAL_SERVICE: TodoStoreService | None = None


def get_todo_store_service() -> TodoStoreService:
    """FastAPI dependency provider for TodoStoreService singleton."""
    global _GLOBAL_SERVICE
    if _GLOBAL_SERVICE is None:
        _GLOBAL_SERVICE = TodoStoreService()
    return _GLOBAL_SERVICE
