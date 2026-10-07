"""[POS]: app/schemas/capacity_hitl.py
[INPUT]: HTTP requests for memory capacity status checks, candidate generation, and HITL resolutions.
[OUTPUT]: Pydantic schemas for capacity health reports, proposals, and resolution responses.
"""

from pydantic import BaseModel, Field


class MemoryEntryRefDTO(BaseModel):
    """Reference metadata for candidate memory item in proposal."""

    id: str
    content: str
    content_hash: str
    tags: list[str] = Field(default_factory=list)
    created_at: float
    access_count: int = 0


class CapacityStatusResponse(BaseModel):
    """Current memory capacity ratio and alert level report."""

    total_entries: int
    max_entries: int
    capacity_ratio: float
    alert_level: str
    pending_candidate_count: int
    timestamp: float


class HitlCandidateDTO(BaseModel):
    """Human-in-the-loop candidate proposal for review."""

    candidate_id: str
    action_kind: str
    source_entries: list[MemoryEntryRefDTO]
    proposed_content: str
    reason: str
    confidence: float
    status: str
    created_at: float
    resolved_at: float | None = None
    reviewer_note: str | None = None


class GenerateCandidatesRequest(BaseModel):
    """Request payload to analyze active entries and propose remediation candidates."""

    entries: list[dict[str, str | int | float | list[str]]] = Field(
        default_factory=list, description="Candidate entries to analyze."
    )
    max_entries: int | None = Field(default=None, description="Optional capacity cap override.")
    max_proposals: int = Field(default=10, ge=1, le=50, description="Max candidate proposals.")


class GenerateCandidatesResponse(BaseModel):
    """Response containing formulated HITL remediation proposals."""

    total_proposals: int
    proposals: list[HitlCandidateDTO]


class ResolveCandidateRequest(BaseModel):
    """Resolution decision submitted by human reviewer."""

    decision: str = Field(..., description="Decision choice: approved or rejected.")
    reviewer_note: str = Field(default="", description="Reviewer comments or audit notes.")
    current_entry_hashes: dict[str, str] | None = Field(
        default=None, description="Optional entry hash map for CAS conflict defense."
    )


class ResolveCandidateResponse(BaseModel):
    """Result of human resolution action."""

    success: bool
    message: str
    proposal: HitlCandidateDTO | None = None


class ArchivedEntryDTO(BaseModel):
    """Entry stored safely in cold archive."""

    id: str
    content: str
    tags: str
    archived_at: float
    origin_candidate_id: str


class ArchivedEntriesResponse(BaseModel):
    """Listing of soft-archived items."""

    total_count: int
    archived_entries: list[ArchivedEntryDTO]
