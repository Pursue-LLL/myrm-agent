"""REST API router for Goal-Driven Quadruple Retrieval and Reasoner Suite.

[POS]
HTTP API endpoints for query intent decomposition, 4-way parallel recall,
and semantic reasoner reranked memory delivery.
[INPUT]
- app.schemas.quadruple_retrieval: DTO contracts
- app.services.memory.quadruple_retrieval_service: Business service layer
[OUTPUT]
- router: FastAPI router mounted under /memory/retrieval/quadruple
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    ParsedTaskGoal,
    QuadrupleRetrievalReport,
    RerankedMemoryHit,
)

from app.schemas.quadruple_retrieval import (
    IngestMemoryItemRequest,
    MemoryHitDTO,
    QuadrupleSearchRequest,
    QuadrupleSearchResponse,
    ReasonerDecisionKindEnum,
    RetrievalChannelKindEnum,
    TaskGoalDTO,
)
from app.services.memory.quadruple_retrieval_service import (
    QuadrupleRetrievalService,
    get_quadruple_retrieval_service,
)

router = APIRouter(prefix="/retrieval/quadruple", tags=["memory-quadruple-retrieval"])


def _to_goal_dto(goal: ParsedTaskGoal) -> TaskGoalDTO:
    return TaskGoalDTO(
        goal_id=goal.goal_id,
        original_query=goal.original_query,
        explicit_intent=goal.explicit_intent,
        target_entities=list(goal.target_entities),
        extracted_keywords=list(goal.extracted_keywords),
        metadata_filters=dict(goal.metadata_filters),
        temporal_constraints=goal.temporal_constraints,
        confidence=goal.confidence,
        created_at=goal.created_at,
    )


def _to_hit_dto(hit: RerankedMemoryHit) -> MemoryHitDTO:
    return MemoryHitDTO(
        memory_id=hit.memory_id,
        content=hit.content,
        final_rank=hit.final_rank,
        final_score=hit.final_score,
        channels_hit=[RetrievalChannelKindEnum(c.value) for c in hit.channels_hit],
        reasoner_decision=ReasonerDecisionKindEnum(hit.reasoner_decision.value),
        rationale=hit.rationale,
        metadata=dict(hit.metadata),
    )


def _to_search_response(report: QuadrupleRetrievalReport) -> QuadrupleSearchResponse:
    return QuadrupleSearchResponse(
        query=report.query,
        parsed_goal=_to_goal_dto(report.parsed_goal),
        channel_hits_count=dict(report.channel_hits_count),
        fused_candidates_count=report.fused_candidates_count,
        final_hits=[_to_hit_dto(h) for h in report.final_hits],
        latency_ms=report.latency_ms,
        created_at=report.created_at,
    )


@router.post(
    "/search",
    response_model=QuadrupleSearchResponse,
    summary="Execute goal-driven quadruple parallel retrieval and reasoner reranking",
)
def search_memories(
    payload: QuadrupleSearchRequest,
) -> QuadrupleSearchResponse:
    """Run intent decomposition, 4-way parallel recall, and reasoner reranking."""
    svc: QuadrupleRetrievalService = get_quadruple_retrieval_service()
    try:
        report = svc.search(
            query=payload.query,
            scoped_filters=payload.scoped_filters,
            top_k=payload.top_k,
        )
        return _to_search_response(report)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quadruple retrieval failed: {exc}",
        ) from exc


@router.post(
    "/parse-goal",
    response_model=TaskGoalDTO,
    summary="Deconstruct query into explicit goal, entities, and constraints",
)
def parse_task_goal(
    query: str,
) -> TaskGoalDTO:
    """Pre-retrieval decomposition analyzing query intent, entities, and constraints."""
    svc: QuadrupleRetrievalService = get_quadruple_retrieval_service()
    goal = svc.parse_goal(query)
    return _to_goal_dto(goal)


@router.post(
    "/items",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a searchable memory item into local index",
)
def ingest_memory_item(
    payload: IngestMemoryItemRequest,
) -> dict[str, str]:
    """Register a structured memory item for quadruple indexing."""
    svc: QuadrupleRetrievalService = get_quadruple_retrieval_service()
    record = svc.add_item(
        memory_id=payload.memory_id,
        content=payload.content,
        subject=payload.subject,
        predicate=payload.predicate,
        object_value=payload.object_value,
        metadata=payload.metadata,
    )
    return {"status": "created", "memory_id": record.memory_id}


@router.get(
    "/items",
    summary="List all indexed memory items",
)
def list_memory_items() -> List[dict[str, object]]:
    """Retrieve all currently registered memory items."""
    svc: QuadrupleRetrievalService = get_quadruple_retrieval_service()
    items = svc.list_items()
    return [
        {
            "memory_id": it.memory_id,
            "content": it.content,
            "subject": it.subject,
            "predicate": it.predicate,
            "object_value": it.object_value,
            "metadata": it.metadata,
        }
        for it in items
    ]
