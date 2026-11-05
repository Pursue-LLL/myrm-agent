"""[OUTPUT]
CommentCreate, DependencyRequest, DependencyResponse, DependencyListResponse, EdgeListResponse

[POS]
Kanban task link schemas. Comments, dependency edges and the edge list wrappers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CommentCreate(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)
    author: str = Field(default="user", max_length=100)


class DependencyRequest(BaseModel):
    parent_task_id: str


class DependencyResponse(BaseModel):
    parent_task_id: str
    child_task_id: str


class DependencyListResponse(BaseModel):
    items: list[str]
    total: int


class EdgeListResponse(BaseModel):
    items: list[DependencyResponse]
    total: int
