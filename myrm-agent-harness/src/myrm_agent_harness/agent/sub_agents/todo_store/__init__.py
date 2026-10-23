"""
[POS] myrm_agent_harness/agent/sub_agents/todo_store/__init__.py
[INPUT] .hud_reader, .sanitizer, .store, .types
[OUTPUT] SharedTodoStore, SharedTodoHudReader, TodoItem, TodoItemStatus, TodoStoreState, TodoHudProjection, strip_control_characters, sanitize_todo_text, PLAN_DECLARATION_SEMANTIC_NOTE

Facade for shared Todo plan store and terminal-escape safe HUD reader subsystem.
Enforces that plan declarations are never confused with execution evidence and
safeguards HUD/TUI views against ANSI control character poisoning.
"""

from __future__ import annotations

from .hud_reader import SharedTodoHudReader
from .sanitizer import sanitize_todo_text, strip_control_characters
from .store import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_TODO_ITEMS,
    SharedTodoStore,
)
from .types import (
    PLAN_DECLARATION_SEMANTIC_NOTE,
    TodoHudProjection,
    TodoItem,
    TodoItemStatus,
    TodoStoreState,
)

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "MAX_TODO_ITEMS",
    "PLAN_DECLARATION_SEMANTIC_NOTE",
    "SharedTodoHudReader",
    "SharedTodoStore",
    "TodoHudProjection",
    "TodoItem",
    "TodoItemStatus",
    "TodoStoreState",
    "sanitize_todo_text",
    "strip_control_characters",
]
