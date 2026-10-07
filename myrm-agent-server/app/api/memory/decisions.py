"""[POS]: app/api/memory/decisions.py
[INPUT]: HTTP requests for architecture decision lifecycle, confirmation gate, and priority recall.
[OUTPUT]: FastAPI APIRouter endpoints managing engineering decision state machine and lineage.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.memory import (
    DecisionRecord,
    DecisionStatus,
    EngineeringDecisionStore,
    LineageCycleError,
    PendingDecisionCandidate,
)

from app.schemas.decisions import (
    CandidateResponse,
    ConfirmCandidateRequest,
    DecisionPrioritySearchRequest,
    DecisionPrioritySearchResponse,
    DecisionRecallHitResponse,
    DecisionResponse,
    RecordDecisionDirectRequest,
    RejectCandidateRequest,
    StageDecisionCandidateRequest,
)
from app.services.memory.decisions import EngineeringDecisionProvider

router = APIRouter(prefix="/decisions", tags=["engineering_decisions"])


def get_decision_store() -> EngineeringDecisionStore:
    """Dependency resolver returning the active EngineeringDecisionStore."""
    return EngineeringDecisionProvider.get_store()


def _to_decision_response(rec: DecisionRecord) -> DecisionResponse:
    return DecisionResponse(
        id=rec.id,
        title=rec.title,
        text=rec.text,
        rationale=rec.rationale,
        status=str(rec.status),
        supersedes_id=rec.supersedes_id,
        superseded_by=rec.superseded_by,
        scope=rec.scope,
        project_key=rec.project_key,
        source_event=rec.source_event,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
    )


def _to_candidate_response(cand: PendingDecisionCandidate) -> CandidateResponse:
    return CandidateResponse(
        id=cand.id,
        session_id=cand.session_id,
        title=cand.title,
        text=cand.text,
        rationale=cand.rationale,
        supersedes_id=cand.supersedes_id,
        status=str(cand.status),
        project_key=cand.project_key,
        created_at=cand.created_at,
        updated_at=cand.updated_at,
    )


@router.post("/stage")
async def stage_candidate(
    req: StageDecisionCandidateRequest,
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> CandidateResponse | DecisionResponse:
    """Stage a proposed architecture decision candidate or auto-commit if configured."""
    try:
        res = await store.stage_candidate(
            session_id=req.session_id,
            title=req.title,
            text=req.text,
            rationale=req.rationale,
            supersedes_id=req.supersedes_id,
            project_key=req.project_key,
        )
        if isinstance(res, DecisionRecord):
            return _to_decision_response(res)
        return _to_candidate_response(res)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm", response_model=DecisionResponse)
async def confirm_candidate(
    req: ConfirmCandidateRequest,
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> DecisionResponse:
    """Approve a pending candidate, transitioning it to an active DecisionRecord."""
    try:
        decision = await store.approve_candidate(req.candidate_id)
        return _to_decision_response(decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, LineageCycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reject", response_model=CandidateResponse)
async def reject_candidate(
    req: RejectCandidateRequest,
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> CandidateResponse:
    """Reject a staged decision candidate."""
    try:
        candidate = await store.reject_candidate(req.candidate_id)
        return _to_candidate_response(candidate)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/direct", response_model=DecisionResponse)
async def record_decision_direct(
    req: RecordDecisionDirectRequest,
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> DecisionResponse:
    """Directly record an active architectural decision."""
    try:
        decision = await store.record_decision(
            title=req.title,
            text=req.text,
            rationale=req.rationale,
            supersedes_id=req.supersedes_id,
            scope=req.scope,
            project_key=req.project_key,
            source_event=req.source_event,
        )
        return _to_decision_response(decision)
    except (ValueError, LineageCycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/list", response_model=list[DecisionResponse])
async def list_decisions(
    project_key: str = Query(default="default"),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> list[DecisionResponse]:
    """List recorded decisions for a given project key."""
    parsed_status = DecisionStatus(status) if status else None
    records = await store.db.list_decisions(
        project_key=project_key, status=parsed_status, limit=limit
    )
    return [_to_decision_response(r) for r in records]


@router.get("/lineage/{decision_id}", response_model=list[DecisionResponse])
async def get_decision_lineage(
    decision_id: str,
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> list[DecisionResponse]:
    """Retrieve full chronological evolution lineage leading to this decision."""
    chain = await store.get_lineage(decision_id)
    if not chain:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' not found.")
    return [_to_decision_response(r) for r in chain]


@router.post("/search_priority", response_model=DecisionPrioritySearchResponse)
async def search_priority(
    req: DecisionPrioritySearchRequest,
    store: EngineeringDecisionStore = Depends(get_decision_store),
) -> DecisionPrioritySearchResponse:
    """Retrieve top-priority decisions with MMR diversification and format prompt block."""
    hits = await store.search_priority(
        query=req.query, project_key=req.project_key, limit=req.limit
    )
    prompt_block = await store.format_priority_prompt(
        query=req.query, project_key=req.project_key, limit=req.limit
    )
    serialized_hits = [
        DecisionRecallHitResponse(
            decision_id=h.decision_id,
            title=h.title,
            text=h.text,
            rationale=h.rationale,
            status=str(h.status),
            supersedes_id=h.supersedes_id,
            superseded_by=h.superseded_by,
            score=h.score,
            is_priority=h.is_priority,
            formatted_line=h.formatted_line,
            source_event=h.source_event,
            created_at=h.created_at,
        )
        for h in hits
    ]
    return DecisionPrioritySearchResponse(hits=serialized_hits, prompt_block=prompt_block)
