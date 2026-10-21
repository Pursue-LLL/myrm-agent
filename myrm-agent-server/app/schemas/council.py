"""Pydantic V2 schemas for Council of Agents Multi-Model Deliberation Protocol (Item 65).

[INPUT]
- CreateCouncilSessionRequest, SubmitProposalRequest, SubmitCritiqueRequest, SubmitRebuttalRequest, AdvancePhaseRequest.

[OUTPUT]
- CouncilSessionDTO, CouncilProposalDTO, CritiqueItemDTO, ConsensusVerdictDTO.

[POS]
- Server-side DTO layer for Item 65 multi-model council deliberation and arbitration.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class DeliberationPhaseDTOEnum(enum.StrEnum):
    """Discrete phases of the multi-model council deliberation protocol."""

    BLIND_PROPOSAL = "blind_proposal"
    CROSS_CRITIQUE = "cross_critique"
    REBUTTAL = "rebuttal"
    CONSENSUS_SYNTHESIS = "consensus_synthesis"
    FINALIZED = "finalized"


class CouncilMemberTierDTOEnum(enum.StrEnum):
    """Persona role tiers within the deliberative council."""

    LEAD = "lead"
    SPECIALIST = "specialist"
    SKEPTIC = "skeptic"
    SYNTHESIZER = "synthesizer"


class CritiqueSeverityDTOEnum(enum.StrEnum):
    """Impact severity of a cross-model critique point."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKER = "blocker"


class CouncilProposalDTO(BaseModel):
    """DTO representing an independent blind proposal submitted by a base model."""

    model_config = ConfigDict(frozen=True)

    proposal_id: str = Field(..., min_length=1)
    member_id: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    reasoning_steps: list[str] = Field(default_factory=list)
    key_arguments: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.85, ge=0.0, le=1.0)


class CritiqueItemDTO(BaseModel):
    """DTO representing an anonymous cross-model critique point."""

    model_config = ConfigDict(frozen=True)

    critique_id: str = Field(..., min_length=1)
    source_member_id: str = Field(..., min_length=1)
    target_member_id: str = Field(..., min_length=1)
    target_proposal_id: str = Field(..., min_length=1)
    critique_points: list[str] = Field(default_factory=list)
    severity: CritiqueSeverityDTOEnum = Field(default=CritiqueSeverityDTOEnum.MEDIUM)
    defense_rebuttal: str | None = Field(default=None)


class ConsensusVerdictDTO(BaseModel):
    """DTO representing the synthesized arbitration and final consensus verdict."""

    model_config = ConfigDict(frozen=True)

    verdict_id: str = Field(..., min_length=1)
    final_decision: str = Field(..., min_length=1)
    confidence_rating: float = Field(default=0.0, ge=0.0, le=1.0)
    key_tradeoffs: list[str] = Field(default_factory=list)
    participating_models: list[str] = Field(default_factory=list)
    dissenting_opinions: list[str] = Field(default_factory=list)


class CouncilSessionDTO(BaseModel):
    """DTO representing the full state of a multi-model council session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1)
    deliberation_topic: str = Field(..., min_length=1)
    phase: DeliberationPhaseDTOEnum = Field(default=DeliberationPhaseDTOEnum.BLIND_PROPOSAL)
    proposals: dict[str, CouncilProposalDTO] = Field(default_factory=dict)
    critiques: list[CritiqueItemDTO] = Field(default_factory=list)
    consensus: ConsensusVerdictDTO | None = Field(default=None)
    created_at: float = Field(default=0.0)
    updated_at: float = Field(default=0.0)


class CreateCouncilSessionRequest(BaseModel):
    """Payload to initialize a new deliberation council session."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1)
    deliberation_topic: str = Field(..., min_length=1)


class SubmitProposalRequest(BaseModel):
    """Payload to submit an independent model proposal."""

    model_config = ConfigDict(frozen=True)

    proposal: CouncilProposalDTO = Field(...)


class SubmitCritiqueRequest(BaseModel):
    """Payload to post a cross-model critique."""

    model_config = ConfigDict(frozen=True)

    critique: CritiqueItemDTO = Field(...)


class SubmitRebuttalRequest(BaseModel):
    """Payload to add a defense rebuttal to a critique point."""

    model_config = ConfigDict(frozen=True)

    rebuttal_text: str = Field(..., min_length=1)


class AdvancePhaseRequest(BaseModel):
    """Payload to advance the deliberation session to the next phase."""

    model_config = ConfigDict(frozen=True)

    target_phase: DeliberationPhaseDTOEnum | None = Field(default=None)
