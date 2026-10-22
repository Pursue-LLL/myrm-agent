"""
[POS] app/schemas/todo_store.py
[INPUT] typing, pydantic
[OUTPUT] TodoItemStatusLiteral, TodoItemDTO, CreateTodoItemRequestDTO, UpdateTodoItemRequestDTO, TodoHudProjectionDTO, TodoListResponseDTO

Pydantic schemas for shared Todo plan store and terminal-escape safe HUD projections.
Enforces explicit contract: "Todo items are plan declarations, not execution evidence."
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

TodoItemStatusLiteral = Literal[
    "pending",
    "in_progress",
    "completed",
    "cancelled",
]

DEFAULT_PLAN_SEMANTIC_CONTRACT: str = (
    "Todo items are plan declarations, not execution evidence."
)


class TodoItemDTO(BaseModel):
    """Data transfer representation of an individual plan item."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(..., min_length=1, max_length=40, description="Unique plan item ID")
    title: str = Field(..., min_length=1, max_length=80, description="Sanitized plan title")
    description: str = Field(default="", max_length=200, description="Sanitized plan description")
    status: TodoItemStatusLiteral = Field(default="pending", description="Plan item status")
    assignee: str = Field(default="", max_length=40, description="Assigned role or agent name")
    created_at: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    updated_at: float = Field(default_factory=time.time, description="Last update epoch timestamp")


class CreateTodoItemRequestDTO(BaseModel):
    """Payload to declare a new plan item in shared store."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=80, description="Plan title (max 80 chars)")
    description: str = Field(default="", max_length=200, description="Optional details (max 200 chars)")
    assignee: str = Field(default="", max_length=40, description="Optional assignee role")
    item_id: str | None = Field(default=None, max_length=40, description="Optional custom item ID")


class UpdateTodoItemRequestDTO(BaseModel):
    """Payload to modify an existing plan item."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=80, description="Updated plan title")
    description: str | None = Field(default=None, max_length=200, description="Updated description")
    status: TodoItemStatusLiteral | None = Field(default=None, description="Updated status")
    assignee: str | None = Field(default=None, max_length=40, description="Updated assignee")


class TodoHudProjectionDTO(BaseModel):
    """Sanitized read-only HUD projection for terminal and WebUI."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session ID")
    total_count: int = Field(ge=0, description="Total declared items")
    pending_count: int = Field(ge=0, description="Pending items count")
    in_progress_count: int = Field(ge=0, description="In-progress items count")
    completed_count: int = Field(ge=0, description="Completed items count")
    cancelled_count: int = Field(ge=0, description="Cancelled items count")
    progress_pct: float = Field(ge=0.0, le=100.0, description="Completion percentage")
    active_items: list[TodoItemDTO] = Field(default_factory=list, description="Currently active items")
    formatted_hud_lines: list[str] = Field(default_factory=list, description="Safe formatted HUD lines")
    semantic_contract: str = Field(
        default=DEFAULT_PLAN_SEMANTIC_CONTRACT,
        description="Explicit plan declaration semantic note",
    )


class TodoListResponseDTO(BaseModel):
    """Collection response containing declared plan items."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session ID")
    items: list[TodoItemDTO] = Field(default_factory=list, description="List of plan items")
    total_count: int = Field(ge=0, description="Item count")
    semantic_contract: str = Field(
        default=DEFAULT_PLAN_SEMANTIC_CONTRACT,
        description="Explicit plan declaration semantic note",
    )
