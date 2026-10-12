"""Pydantic schemas for Person Card and relationship memory suite.

[INPUT]
- Personal profiles, relationship attributes, interaction logs, and pre-action verification payloads.

[OUTPUT]
- PersonCardDTO, PersonAttributesDTO, PreActionCheckRequestDTO, PreActionCheckResponseDTO,
  CreatePersonCardRequest, UpdatePersonCardRequest, MergePersonCardRequest.

[POS]
- Server-side DTO contracts for Item 155 PersonCardAndRelationshipMemoryLayer.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RelationTypeDTO = Literal[
    "self",
    "family",
    "colleague",
    "client",
    "vendor",
    "recruiter",
    "friend",
    "other",
]

DecayStatusDTO = Literal["active", "weak", "archived"]

ActionTypeDTO = Literal[
    "send_invite",
    "send_email",
    "create_group",
    "assign_task",
    "submit_approval",
    "other",
]


class PersonAttributesDTO(BaseModel):
    """Personal attributes and dietary/working habits."""

    dietary_restrictions: list[str] = Field(default_factory=list)
    birthday: str | None = None
    timezone: str | None = None
    preferred_contact_hours: str | None = None
    approval_preference: str | None = None
    custom_notes: dict[str, str] = Field(default_factory=dict)


class PersonInteractionDTO(BaseModel):
    """Interaction history item."""

    timestamp: str
    summary: str
    channel: str | None = None
    source_event_id: str | None = None


class PersonCardDTO(BaseModel):
    """Complete person entity representation."""

    person_id: str
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    relation_type: RelationTypeDTO = "other"
    org: str | None = None
    attributes: PersonAttributesDTO = Field(default_factory=PersonAttributesDTO)
    commitments: list[str] = Field(default_factory=list)
    interaction_timeline: list[PersonInteractionDTO] = Field(default_factory=list)
    last_interaction_at: str | None = None
    confidence: float = 1.0
    scope: Literal["global", "agent"] = "global"
    agent_id: str | None = None
    decay_status: DecayStatusDTO = "active"
    decay_score: float = 1.0


class CreatePersonCardRequest(BaseModel):
    """Request to create a new person card."""

    person_id: str | None = None
    display_name: str
    aliases: list[str] = Field(default_factory=list)
    relation_type: RelationTypeDTO = "other"
    org: str | None = None
    attributes: PersonAttributesDTO = Field(default_factory=PersonAttributesDTO)
    commitments: list[str] = Field(default_factory=list)
    scope: Literal["global", "agent"] = "global"
    agent_id: str | None = None


class UpdatePersonCardRequest(BaseModel):
    """Request to update an existing person card."""

    display_name: str | None = None
    aliases: list[str] | None = None
    relation_type: RelationTypeDTO | None = None
    org: str | None = None
    attributes: PersonAttributesDTO | None = None
    commitments: list[str] | None = None
    confidence: float | None = None
    decay_status: DecayStatusDTO | None = None


class MergePersonCardRequest(BaseModel):
    """Request to merge two person cards."""

    source_person_id: str
    target_person_id: str


class PreActionCheckRequestDTO(BaseModel):
    """Payload to perform pre-action attribute verification."""

    action_type: ActionTypeDTO
    participant_names_or_ids: list[str]
    action_summary: str = ""
    agent_id: str | None = None


class ParticipantAttributeSummaryDTO(BaseModel):
    """Participant check summary."""

    person_id: str
    display_name: str
    relation_type: RelationTypeDTO
    dietary_restrictions: list[str] = Field(default_factory=list)
    timezone: str | None = None
    approval_preference: str | None = None
    missing_critical_attributes: list[str] = Field(default_factory=list)
    is_weak_memory: bool = False
    attributes: PersonAttributesDTO = Field(default_factory=PersonAttributesDTO)


class PreActionCheckResponseDTO(BaseModel):
    """Response containing pre-action check outcome and prompt cues."""

    action_type: ActionTypeDTO
    action_summary: str
    has_missing_attributes: bool
    has_weak_memory_warning: bool
    participants: list[ParticipantAttributeSummaryDTO] = Field(default_factory=list)
    prompt_cue: str = ""
    warnings: list[str] = Field(default_factory=list)
