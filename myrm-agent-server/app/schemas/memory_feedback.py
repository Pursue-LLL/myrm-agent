"""Schemas for natural language memory feedback and live correction API.

[INPUT]
- pydantic BaseModel, Field

[OUTPUT]
- CorrectionDetectRequest, CorrectionDetectResponse
- TargetCandidateDTO, MutationResultDTO
- LiveCorrectionExecuteRequest, LiveCorrectionExecuteResponse

[POS]
app.schemas.memory_feedback
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CorrectionDetectRequest(BaseModel):
    """Request payload to detect correction intent in user utterance."""

    utterance: str = Field(..., min_length=1, max_length=1000, description="Raw user utterance")


class CorrectionDetectResponse(BaseModel):
    """Response payload detailing detected correction intent and extracted slot."""

    detected: bool = Field(..., description="Whether correction signal was detected")
    intent: str | None = Field(default=None, description="Intent type name if detected")
    corrected_value: str | None = Field(default=None, description="Extracted new assertion")
    negated_value: str | None = Field(default=None, description="Extracted negated assertion")
    subject: str | None = Field(default=None, description="Extracted topic or subject")
    confidence: float = Field(default=0.0, description="Detection confidence score")


class TargetCandidateDTO(BaseModel):
    """Candidate memory node for targeted correction."""

    memory_id: str = Field(..., description="Identifier of candidate memory node")
    content: str = Field(..., description="Text content of candidate memory node")
    cube_id: str | None = Field(default=None, description="Optional scoped memory cube ID")
    match_score: float = Field(default=1.0, description="Pre-computed relevance score")


class MutationResultDTO(BaseModel):
    """Details of physical memory state change."""

    action: str = Field(..., description="Action taken: supersede, retract, amend, create_novel")
    target_memory_id: str | None = Field(default=None, description="ID of affected target memory")
    new_memory_id: str | None = Field(default=None, description="ID of newly created memory node")
    status: str = Field(..., description="Execution status")
    superseded_content: str | None = Field(default=None, description="Archived content")
    new_content: str | None = Field(default=None, description="Active replacement content")


class LiveCorrectionExecuteRequest(BaseModel):
    """Request payload to execute live memory correction and return user acknowledgement."""

    utterance: str = Field(..., min_length=1, max_length=1000, description="Raw user utterance")
    candidates: list[TargetCandidateDTO] = Field(
        default_factory=list,
        description="Optional pre-fetched candidate nodes to localize against",
    )


class LiveCorrectionExecuteResponse(BaseModel):
    """Response payload containing generated acknowledgement and mutation record."""

    success: bool = Field(..., description="Whether live correction was successfully processed")
    ack_message: str = Field(..., description="Conversational acknowledgement message")
    intent: str = Field(..., description="Detected intent kind")
    mutation: MutationResultDTO | None = Field(default=None, description="Mutation result details")
    processing_ms: float = Field(default=0.0, description="Execution latency in milliseconds")
