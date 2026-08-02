"""FAQ management API endpoints.

[INPUT]
- app.database.models.faq::FaqEntry (POS: FAQ 语义缓存域模型)
- app.services.faq (POS: FAQ service layer)

[OUTPUT]
- router: FastAPI router with FAQ CRUD, index rebuild, stats, and unmatched queries

[POS]
REST API for per-agent FAQ corpus management. Provides CRUD for Q&A entries,
corpus settings, bulk import, index rebuild, analytics, and unmatched query discovery.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.database.models.faq import FaqEntry
from app.services.faq.corpus import FaqCorpusService
from app.services.faq.tracker import FaqHitTracker

from .schemas import (
    FaqBulkImportRequest,
    FaqCorpusResponse,
    FaqCorpusSettingsRequest,
    FaqEntryRequest,
    FaqEntryResponse,
    FaqEntryUpdateRequest,
    FaqRebuildResponse,
    FaqStatsResponse,
    FaqUnmatchedItem,
)

logger = logging.getLogger(__name__)
router = APIRouter()

_corpus_service = FaqCorpusService()
_tracker = FaqHitTracker()


def _entry_to_response(entry: FaqEntry) -> FaqEntryResponse:
    return FaqEntryResponse(
        id=entry.id,
        corpus_id=entry.corpus_id,
        question=entry.question,
        answer=entry.answer,
        tags=entry.tags,
        sort_order=entry.sort_order,
        created_at=entry.created_at.isoformat(),
        updated_at=entry.updated_at.isoformat(),
    )


@router.get("/{agent_id}/corpus")
async def get_corpus(agent_id: str) -> FaqCorpusResponse:
    corpus = await _corpus_service.get_or_create_corpus(agent_id)
    entries = await _corpus_service.list_entries(agent_id)
    return FaqCorpusResponse(
        id=corpus.id,
        agent_id=corpus.agent_id,
        enabled=corpus.enabled,
        threshold=corpus.threshold,
        min_score_gap=corpus.min_score_gap,
        entry_count=len(entries),
    )


@router.patch("/{agent_id}/corpus")
async def update_corpus_settings(
    agent_id: str,
    body: FaqCorpusSettingsRequest,
) -> FaqCorpusResponse:
    corpus = await _corpus_service.update_corpus_settings(
        agent_id,
        enabled=body.enabled,
        threshold=body.threshold,
        min_score_gap=body.min_score_gap,
    )
    entries = await _corpus_service.list_entries(agent_id)
    return FaqCorpusResponse(
        id=corpus.id,
        agent_id=corpus.agent_id,
        enabled=corpus.enabled,
        threshold=corpus.threshold,
        min_score_gap=corpus.min_score_gap,
        entry_count=len(entries),
    )


@router.get("/{agent_id}/entries")
async def list_entries(agent_id: str) -> list[FaqEntryResponse]:
    entries = await _corpus_service.list_entries(agent_id)
    return [_entry_to_response(e) for e in entries]


@router.post("/{agent_id}/entries", status_code=status.HTTP_201_CREATED)
async def create_entry(agent_id: str, body: FaqEntryRequest) -> FaqEntryResponse:
    entry = await _corpus_service.add_entry(agent_id, body.question, body.answer, body.tags)
    return _entry_to_response(entry)


@router.put("/entries/{entry_id}")
async def update_entry(entry_id: str, body: FaqEntryUpdateRequest) -> FaqEntryResponse:
    entry = await _corpus_service.update_entry(
        entry_id,
        question=body.question,
        answer=body.answer,
        tags=body.tags,
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="FAQ entry not found")
    return _entry_to_response(entry)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entry(entry_id: str) -> None:
    deleted = await _corpus_service.delete_entry(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="FAQ entry not found")


@router.post("/{agent_id}/import")
async def bulk_import(agent_id: str, body: FaqBulkImportRequest) -> dict[str, int]:
    items = [{"question": i.question, "answer": i.answer, "tags": i.tags} for i in body.items]
    count = await _corpus_service.bulk_import(agent_id, items)
    return {"imported": count}


@router.post("/{agent_id}/rebuild-index")
async def rebuild_index(agent_id: str) -> FaqRebuildResponse:
    from app.core.retriever.vector.defaults import create_default_vector_store
    from myrm_agent_harness.toolkits.retriever.embedding.factory import (
        get_embedding_config,
        get_embedding_service,
    )

    embedding_service = get_embedding_service(get_embedding_config())
    vector_store = await create_default_vector_store()
    if vector_store is None:
        raise HTTPException(status_code=503, detail="Vector store unavailable")

    count = await _corpus_service.rebuild_index(agent_id, embedding_service, vector_store)
    return FaqRebuildResponse(indexed=count)


@router.get("/{agent_id}/stats")
async def get_stats(agent_id: str) -> FaqStatsResponse:
    corpus = await _corpus_service.get_or_create_corpus(agent_id)
    stats = await _tracker.get_stats(corpus.id)
    total = stats["total"]
    return FaqStatsResponse(
        total=total,
        hits=stats["hits"],
        misses=stats["misses"],
        hit_rate=stats["hits"] / total if total > 0 else 0.0,
    )


@router.get("/{agent_id}/unmatched")
async def list_unmatched(agent_id: str, limit: int = 50) -> list[FaqUnmatchedItem]:
    corpus = await _corpus_service.get_or_create_corpus(agent_id)
    items = await _tracker.list_unmatched(corpus.id, limit=min(limit, 200))
    return [FaqUnmatchedItem(**item) for item in items]
