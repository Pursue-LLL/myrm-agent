"""Context search API schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContextSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=20)


class ContextSearchHit(BaseModel):
    source: Literal["memory", "workspace_file"]
    rank: int
    score: float
    title: str
    snippet: str
    reference: str


class ContextSearchResponse(BaseModel):
    query: str
    hits: list[ContextSearchHit] = Field(default_factory=list)
    memory_count: int = 0
    file_count: int = 0
    search_time_ms: float = 0.0
