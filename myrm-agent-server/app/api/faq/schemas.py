"""Pydantic schemas for FAQ API endpoints.

[POS] Request/response models used by ``router.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class FaqCorpusSettingsRequest(BaseModel):
    enabled: bool | None = None
    threshold: float | None = Field(default=None, ge=0.75, le=1.0)
    min_score_gap: float | None = Field(default=None, ge=0.0, le=0.5)


class FaqCorpusResponse(BaseModel):
    id: str
    agent_id: str
    enabled: bool
    threshold: float
    min_score_gap: float
    entry_count: int = 0


class FaqEntryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    answer: str = Field(..., min_length=1, max_length=10000)
    tags: str = Field(default="", max_length=512)


class FaqEntryUpdateRequest(BaseModel):
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    answer: str | None = Field(default=None, min_length=1, max_length=10000)
    tags: str | None = Field(default=None, max_length=512)


class FaqEntryResponse(BaseModel):
    id: str
    corpus_id: str
    question: str
    answer: str
    tags: str
    sort_order: int
    created_at: str
    updated_at: str


class FaqBulkImportRequest(BaseModel):
    items: list[FaqEntryRequest] = Field(..., min_length=1, max_length=500)


class FaqStatsResponse(BaseModel):
    total: int
    hits: int
    misses: int
    hit_rate: float


class FaqUnmatchedItem(BaseModel):
    query: str
    top_score: float
    time: str


class FaqRebuildResponse(BaseModel):
    indexed: int
