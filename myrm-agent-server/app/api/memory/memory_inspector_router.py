"""Memory Inspector & Epistemic Veracity Governance API Router.

[INPUT]
- Session ID, Memory ID, PromoteMemoryRequest, CorrectMemoryRequest

[OUTPUT]
- GET /api/v1/memory/inspect/session/{session_id}
- POST /api/v1/memory/inspect/{memory_id}/promote
- POST /api/v1/memory/inspect/{memory_id}/correct
- DELETE /api/v1/memory/inspect/{memory_id}/forget

[POS]
Item 30 server layer: Epistemic veracity grading (assertion/observation/belief),
session memory citation inspection, and atomic governance (promote/correct/forget).
Strictly under 250 lines. Zero `Any`.
"""

from __future__ import annotations

import logging
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inspect", tags=["memory-inspector"])

EpistemicTier = Literal["assertion", "observation", "belief"]


class EpistemicMemoryItem(BaseModel):
    """Memory item with epistemic veracity tier and attribution lineage."""

    id: str = Field(..., description="Unique memory record ID")
    content: str = Field(..., description="Actual text content of the memory")
    epistemic_tier: EpistemicTier = Field(..., description="Epistemic grade: assertion (1.0), observation (0.8), belief (0.5)")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Normalized epistemic confidence score")
    similarity_score: float = Field(default=0.85, ge=0.0, le=1.0, description="Semantic recall similarity score")
    source_session_id: str | None = Field(default=None, description="Original session ID where this memory was formed")
    hit_count: int = Field(default=1, ge=0, description="Recall hit count across agent lifetime")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    last_recalled_at: str | None = Field(default=None, description="ISO 8601 last recall timestamp")
    provenance_chain: list[str] = Field(default_factory=list, description="Audit chain of evidence sources")


class InspectSessionMemoriesResponse(BaseModel):
    """Response containing memories recalled and cited in the specified session."""

    session_id: str
    memories: list[EpistemicMemoryItem]
    total_count: int


class PromoteMemoryRequest(BaseModel):
    """Request to promote a low-confidence belief to high-confidence assertion."""

    target_tier: Literal["assertion", "observation"] = Field(
        default="assertion",
        description="Upgraded epistemic tier",
    )
    justification: str | None = Field(
        default=None,
        description="Optional operator reason for promotion",
    )


class CorrectMemoryRequest(BaseModel):
    """Request to edit memory text in-place with atomic re-indexing."""

    new_content: str = Field(..., min_length=1, description="Sanitized and corrected memory text")
    reason: str | None = Field(default=None, description="Optional correction explanation")


# In-memory storage vault for session memory inspection & mutations (single-node sandbox)
_MEMORY_VAULT: dict[str, EpistemicMemoryItem] = {
    "mem_mock_1": EpistemicMemoryItem(
        id="mem_mock_1",
        content="User preferred dark theme and high-contrast accessibility mode.",
        epistemic_tier="assertion",
        confidence_score=1.0,
        similarity_score=0.96,
        source_session_id="session_init",
        hit_count=12,
        created_at="2026-08-01T10:00:00Z",
        last_recalled_at="2026-08-31T14:20:00Z",
        provenance_chain=["explicit_user_prompt: 'always use dark theme'"],
    ),
    "mem_mock_2": EpistemicMemoryItem(
        id="mem_mock_2",
        content="Node.js version is v20.14.0 inside current sandbox workspace.",
        epistemic_tier="observation",
        confidence_score=0.85,
        similarity_score=0.91,
        source_session_id="session_tooling",
        hit_count=5,
        created_at="2026-08-15T08:30:00Z",
        last_recalled_at="2026-08-31T14:20:00Z",
        provenance_chain=["tool_execution: run_command('node --version')"],
    ),
    "mem_mock_3": EpistemicMemoryItem(
        id="mem_mock_3",
        content="User likely prefers TypeScript over vanilla JavaScript for new components.",
        epistemic_tier="belief",
        confidence_score=0.6,
        similarity_score=0.78,
        source_session_id="session_coding",
        hit_count=3,
        created_at="2026-08-20T12:00:00Z",
        last_recalled_at="2026-08-31T14:20:00Z",
        provenance_chain=["agent_inference: '3 recent files created with .tsx extension'"],
    ),
}

# Session citation index: session_id -> list of memory_ids
_SESSION_CITATIONS: dict[str, list[str]] = {
    "default_session": ["mem_mock_1", "mem_mock_2", "mem_mock_3"],
}


@router.get("/session/{session_id}", response_model=InspectSessionMemoriesResponse)
async def get_session_memories(session_id: str) -> InspectSessionMemoriesResponse:
    """Retrieve all cited memories for the given session with epistemic grading."""
    # If session not explicitly registered, provide default representative set for testing
    cited_ids = _SESSION_CITATIONS.get(session_id) or ["mem_mock_1", "mem_mock_2", "mem_mock_3"]
    memories: list[EpistemicMemoryItem] = []
    for mid in cited_ids:
        item = _MEMORY_VAULT.get(mid)
        if item is not None:
            memories.append(item)

    return InspectSessionMemoriesResponse(
        session_id=session_id,
        memories=memories,
        total_count=len(memories),
    )


@router.post("/{memory_id}/promote", response_model=EpistemicMemoryItem)
async def promote_memory_tier(memory_id: str, request: PromoteMemoryRequest) -> EpistemicMemoryItem:
    """Promote an inferred belief into a grounded assertion or verified observation."""
    item = _MEMORY_VAULT.get(memory_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{memory_id}' not found.",
        )

    new_score = 1.0 if request.target_tier == "assertion" else 0.85
    new_provenance = list(item.provenance_chain)
    new_provenance.append(f"operator_promoted: {request.justification or 'Verified by human operator'}")

    updated = EpistemicMemoryItem(
        id=item.id,
        content=item.content,
        epistemic_tier=request.target_tier,
        confidence_score=new_score,
        similarity_score=item.similarity_score,
        source_session_id=item.source_session_id,
        hit_count=item.hit_count,
        created_at=item.created_at,
        last_recalled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        provenance_chain=new_provenance,
    )
    _MEMORY_VAULT[memory_id] = updated
    return updated


@router.post("/{memory_id}/correct", response_model=EpistemicMemoryItem)
async def correct_memory_content(memory_id: str, request: CorrectMemoryRequest) -> EpistemicMemoryItem:
    """In-place atomic edit of memory text with provenance tracking."""
    item = _MEMORY_VAULT.get(memory_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{memory_id}' not found.",
        )

    new_provenance = list(item.provenance_chain)
    new_provenance.append(f"operator_corrected: {request.reason or 'Corrected text content'}")

    updated = EpistemicMemoryItem(
        id=item.id,
        content=request.new_content,
        epistemic_tier=item.epistemic_tier,
        confidence_score=item.confidence_score,
        similarity_score=item.similarity_score,
        source_session_id=item.source_session_id,
        hit_count=item.hit_count,
        created_at=item.created_at,
        last_recalled_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        provenance_chain=new_provenance,
    )
    _MEMORY_VAULT[memory_id] = updated
    return updated


@router.delete("/{memory_id}/forget", status_code=status.HTTP_204_NO_CONTENT)
async def forget_memory_item(memory_id: str) -> None:
    """Physically forget and erase the memory record from storage and citation indices."""
    if memory_id not in _MEMORY_VAULT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory record '{memory_id}' not found.",
        )

    _MEMORY_VAULT.pop(memory_id, None)
    for session_id, cids in list(_SESSION_CITATIONS.items()):
        if memory_id in cids:
            _SESSION_CITATIONS[session_id] = [cid for cid in cids if cid != memory_id]
