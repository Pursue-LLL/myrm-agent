"""Mem0-compatible request/response types.

[INPUT]
pydantic::BaseModel (POS: Schema base)

[OUTPUT]
Mem0-wire-format request/response models for the compatibility layer.

[POS]
Defines the exact JSON shapes that the Mem0 SDK expects.
These types mirror Mem0's v1/v3 API contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Mem0AddRequest(BaseModel):
    """POST /v3/memories/add/ request body."""

    messages: list[dict[str, str]] = Field(..., min_length=1)
    user_id: str | None = None
    agent_id: str | None = None
    app_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] | None = None
    filters: dict[str, str] | None = None


class Mem0SearchRequest(BaseModel):
    """POST /v3/memories/search/ request body."""

    query: str = Field(..., min_length=1)
    user_id: str | None = None
    agent_id: str | None = None
    app_id: str | None = None
    run_id: str | None = None
    top_k: int = Field(10, ge=1, le=100)
    rerank: bool = False
    filters: dict[str, str] | None = None


class Mem0GetAllRequest(BaseModel):
    """POST /v3/memories/ request body (get_all)."""

    user_id: str | None = None
    agent_id: str | None = None
    app_id: str | None = None
    run_id: str | None = None
    filters: dict[str, str] | None = None


class Mem0UpdateRequest(BaseModel):
    """PUT /v1/memories/{memory_id}/ request body."""

    text: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str | None = None


class Mem0MemoryItem(BaseModel):
    """Single memory item in Mem0 response format."""

    id: str
    memory: str
    hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    user_id: str | None = None
    agent_id: str | None = None
    app_id: str | None = None


class Mem0AddResponse(BaseModel):
    """Response for POST /v3/memories/add/."""

    results: list[Mem0MemoryItem]
    relations: list[dict[str, Any]] = Field(default_factory=list)


class Mem0SearchResultItem(BaseModel):
    """Single search result with score."""

    id: str
    memory: str
    hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float
    created_at: str
    updated_at: str
    user_id: str | None = None


class Mem0SearchResponse(BaseModel):
    """Response for POST /v3/memories/search/."""

    results: list[Mem0SearchResultItem]


class Mem0GetAllResponse(BaseModel):
    """Response for POST /v3/memories/ (get_all, paginated)."""

    count: int
    next: str | None = None
    previous: str | None = None
    results: list[Mem0MemoryItem]


class Mem0PingResponse(BaseModel):
    """Response for GET /v1/ping/."""

    status: str = "ok"
    org_id: str | None = None
    project_id: str | None = None
    user_email: str | None = None


class Mem0DeleteResponse(BaseModel):
    """Response for DELETE /v1/memories/{memory_id}/."""

    message: str = "Memory deleted successfully!"


class Mem0HistoryItem(BaseModel):
    """Single history entry."""

    id: str
    memory_id: str
    old_memory: str | None = None
    new_memory: str | None = None
    event: str
    timestamp: str
    is_deleted: int = 0


def datetime_to_mem0_str(dt: datetime) -> str:
    """Convert datetime to Mem0's expected ISO string format."""
    return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
