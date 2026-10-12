"""Schemas for Natural Language Memory Feedback and Live Correction Suite.

[POS]
Pydantic DTO contracts for conversational correction intent detection, candidate localization,
atomic memory state mutations, and user-facing acknowledgement receipts. Strictly typed without Any.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class CorrectionIntentKindEnum(str, Enum):
    """Categorical intent detected from natural language user feedback."""

    PREFERENCE_UPDATE = "preference_update"
    FACT_SUPERSEDED = "fact_superseded"
    BEHAVIOR_RULE = "behavior_rule"
    RETRACT_MISTAKE = "retract_mistake"
    GENERAL_AMENDMENT = "general_amendment"


class MutationActionEnum(str, Enum):
    """Atomic mutation operation executed on target memory items."""

    SUPERSEDE = "supersede"
    RETRACT = "retract"
    AMEND = "amend"
    CREATE_NOVEL = "create_novel"


class CorrectionSlotDTO(BaseModel):
    """Extracted semantic slots from user correction utterance."""

    corrected_value: str = Field(..., description="Target corrected assertion or value")
    negated_value: Optional[str] = Field(None, description="Previous assertion or preference being negated")
    subject: Optional[str] = Field(None, description="Subject entity associated with the correction")
    intent: CorrectionIntentKindEnum = Field(..., description="Classified correction intent kind")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    raw_utterance: str = Field(default="", description="Original conversational utterance")


class TargetNodeCandidateDTO(BaseModel):
    """Memory item candidate targeted for mutation."""

    memory_id: str = Field(..., description="Unique memory item ID")
    content: str = Field(..., description="Text content of the existing memory item")
    cube_id: Optional[str] = Field(None, description="Target memory cube identifier if partitioned")
    match_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Calculated similarity match score")
    attributes: Dict[str, str] = Field(default_factory=dict, description="Metadata key-value pairs")


class LiveCorrectionMutationResultDTO(BaseModel):
    """Atomic execution result of a live correction mutation."""

    action: MutationActionEnum = Field(..., description="Applied mutation action")
    target_memory_id: Optional[str] = Field(None, description="Superseded or retracted memory item ID")
    new_memory_id: Optional[str] = Field(None, description="Newly created active memory item ID")
    status: str = Field(..., description="Execution status ('applied', 'retracted', 'created')")
    superseded_content: Optional[str] = Field(None, description="Previous content now marked obsolete")
    new_content: Optional[str] = Field(None, description="New canonical content")
    audit_trail: Dict[str, str] = Field(default_factory=dict, description="Audit and lineage traceability metadata")
    timestamp: str = Field(..., description="ISO 8601 mutation timestamp")


class CorrectionAckReceiptDTO(BaseModel):
    """High-level receipt with user-facing acknowledgement text."""

    success: bool = Field(..., description="Whether live correction succeeded")
    ack_message: str = Field(..., description="Natural language acknowledgement synthesized for user")
    intent: CorrectionIntentKindEnum = Field(..., description="Detected intent kind")
    slot: CorrectionSlotDTO = Field(..., description="Extracted semantic slot payload")
    mutated_record: Optional[LiveCorrectionMutationResultDTO] = Field(
        None, description="Associated atomic mutation details"
    )
    processing_ms: float = Field(default=0.0, ge=0.0, description="Pipeline latency in milliseconds")


class ProcessUtteranceRequest(BaseModel):
    """Request payload to process a conversational utterance for live correction."""

    utterance: str = Field(..., min_length=1, max_length=1000, description="User conversational utterance")
    candidates: Optional[List[TargetNodeCandidateDTO]] = Field(
        None, description="Optional explicit candidate memory items; if omitted, active service store items are used"
    )


class SeedCandidateRequest(BaseModel):
    """Request payload to register a candidate memory node into active service pool."""

    memory_id: str = Field(..., description="Candidate memory item ID")
    content: str = Field(..., description="Candidate textual content")
    cube_id: Optional[str] = Field(None, description="Cube partition name")
    attributes: Optional[Dict[str, str]] = Field(None, description="Key-value metadata attributes")


class LiveCorrectionHistoryResponse(BaseModel):
    """Response payload containing mutation history."""

    history: List[LiveCorrectionMutationResultDTO] = Field(default_factory=list, description="Historical mutations")
    total: int = Field(..., description="Total count of recorded mutations")


class LiveCorrectionStatusResponse(BaseModel):
    """Status report for the live correction engine service."""

    service_status: str = Field(default="ready", description="Engine health status")
    candidates_count: int = Field(..., description="Total active candidates in memory pool")
    mutations_count: int = Field(..., description="Total executed mutations")
