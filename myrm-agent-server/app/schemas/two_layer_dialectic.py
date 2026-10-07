# [POS]: app/schemas/two_layer_dialectic.py
# [INPUT]: None (Standard library & Pydantic)
# [OUTPUT]: DialecticConflictCandidateDTO, DialecticReconciliationResultDTO, BaseContextPayloadDTO, TwoLayerContextInjectionResultDTO, DialecticInspectRequest, DialecticReconcileRequest, AssembleInjectionRequest

"""Pydantic schemas and DTOs for Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation Suite (Item 112)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DialecticConflictCandidateDTO(BaseModel):
    """DTO representing a detected cognitive contradiction pair."""

    statement_a: str = Field(description="Historical memory statement")
    statement_b: str = Field(description="Competing recent memory statement")
    subject_domain: str = Field(description="Categorical domain or overlapping subject")
    conflict_score: float = Field(default=1.0, description="Exclusivity score between 0.0 and 1.0")


class DialecticReconciliationResultDTO(BaseModel):
    """DTO representing the authoritative dialectic resolution of a memory conflict."""

    passes_executed: list[str] = Field(
        default_factory=list, description="Reasoning passes executed (inspection, synthesis, reconciliation)"
    )
    resolved_statement: str = Field(description="Harmonized authoritative decision statement")
    superseded_statements: list[str] = Field(
        default_factory=list, description="Superseded statements retired during resolution"
    )
    confidence: float = Field(default=1.0, description="Confidence score of resolution")
    rationale: str = Field(default="", description="Dialectic reasoning trace")


class BaseContextPayloadDTO(BaseModel):
    """DTO for Layer 1 Base Context maintaining deterministic Prompt KV Cache."""

    session_summary: str = Field(description="Trajectory synopsis of current session")
    standing_peer_cards: list[str] = Field(
        default_factory=list, description="Standing persona summaries for active peers"
    )
    cache_control_hash: str = Field(description="Deterministic SHA-256 fingerprint for KV Cache stability")
    refreshed_at_turn: int = Field(default=0, description="Turn index when this base context was refreshed")
    created_at: str = Field(description="Creation ISO timestamp")


class TwoLayerContextInjectionResultDTO(BaseModel):
    """DTO for composite dual-layer injection payload."""

    layer1_base_context: str = Field(description="Static base context XML block (cache-safe prefix)")
    layer2_dialectic_block: str = Field(default="", description="Dialectic resolution block (user message tail)")
    injected_position: str = Field(default="user_message_tail", description="Target injection placement")
    is_cache_safe: bool = Field(default=True, description="True if prefix cache remains untouched")
    token_overhead: int = Field(default=0, description="Estimated total token overhead")


class DialecticInspectRequest(BaseModel):
    """Request payload to scan memory statements for mutual exclusivity."""

    statements: list[str] = Field(min_length=2, description="Candidate memory assertions to inspect")
    cutoff: float = Field(default=0.65, ge=0.0, le=1.0, description="Similarity and conflict threshold")


class DialecticReconcileRequest(BaseModel):
    """Request payload to resolve contradictions among candidate statements."""

    statements: list[str] = Field(min_length=2, description="Candidate assertions containing contradictions")
    depth: int = Field(default=3, ge=1, le=3, description="Dialectic depth: 1, 2, or 3")


class AssembleInjectionRequest(BaseModel):
    """Request payload to assemble dual-layer context blocks with cadence gating."""

    session_id: str = Field(description="Active session identifier")
    turn: int = Field(ge=0, description="Current dialogue turn index")
    session_summary: str = Field(description="Summary of current session trajectory")
    peer_cards: list[str] = Field(default_factory=list, description="Active peer persona card digests")
    candidate_memories: list[str] = Field(default_factory=list, description="Unfiltered memory assertions")
    context_cadence: int = Field(default=5, ge=1, description="Turns between Layer 1 refreshes")
    dialectic_cadence: int = Field(default=3, ge=1, description="Turns between Layer 2 dialectic checks")
    force_refresh_base: bool = Field(default=False, description="Force Layer 1 compilation")
    force_dialectic: bool = Field(default=False, description="Force Layer 2 dialectic resolution")
