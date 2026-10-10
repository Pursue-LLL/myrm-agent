"""Pydantic schemas for Project Experience & ADR Flywheel suite.

[INPUT]
- Narrative logs, experience models, ingestion payloads, and minefield sniffing requests.

[OUTPUT]
- EngineeringExperienceDTO, ExtractExperienceRequestDTO, ExtractExperienceResponseDTO,
  IngestExperienceRequestDTO, IngestExperienceResponseDTO, MinefieldAlertDTO,
  SniffMinefieldRequestDTO, SniffMinefieldResponseDTO.

[POS]
- Server-side DTO contracts for Item 154 ProjectExperienceAndADRFlywheelSuite.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class EngineeringExperienceDTO(BaseModel):
    """Data transfer object for a single engineering experience record."""

    experience_id: str = Field(..., description="Unique experience identifier")
    kind: str = Field(..., description="bug_experience | architectural_decision | convention_rule")
    target_entity: str = Field(..., description="Module, table, API, or system component")
    trigger_condition: str = Field(..., description="Preconditions or invocation pattern")
    root_cause_or_rationale: str = Field(..., description="Root cause or ADR rationale")
    convention_or_remedy: str = Field(..., description="Prescribed convention or fix")
    created_date: str = Field(..., description="Date formatted as YYYY-MM-DD")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")
    confidence: float = Field(default=1.0, description="Confidence score")


class ExtractExperienceRequestDTO(BaseModel):
    """Payload to extract experiences from execution narrative or test failures."""

    narrative: str = Field(..., description="Log trace, test output, or design discussion")
    default_kind: str = Field(default="bug_experience", description="Default kind fallback")


class ExtractExperienceResponseDTO(BaseModel):
    """Response containing extracted experiences."""

    experiences: list[EngineeringExperienceDTO] = Field(default_factory=list)
    total_count: int = 0


class IngestExperienceRequestDTO(BaseModel):
    """Payload to ingest an experience into the causal flywheel."""

    experience: EngineeringExperienceDTO
    workspace_dir: str | None = Field(default=None, description="Optional workspace for dongle sync")


class IngestExperienceResponseDTO(BaseModel):
    """Outcome of ingesting experience into flywheel store."""

    experience_id: str
    kind: str
    target_entity: str
    bound_dongle_block_id: str | None = None
    persisted: bool = True
    message: str = ""


class MinefieldAlertDTO(BaseModel):
    """Proactive alert surfaced when plan touches known danger zones."""

    entity_matched: str
    experience_id: str
    kind: str
    warning_message: str
    convention_to_follow: str
    severity: str = "warning"  # critical | warning | info


class SniffMinefieldRequestDTO(BaseModel):
    """Payload to pre-sniff upcoming execution plan or candidate entities."""

    plan_text: str = Field(..., description="Planned actions or proposed code modifications")
    explicit_entities: list[str] = Field(
        default_factory=list, description="Explicit module or table names being touched"
    )


class SniffMinefieldResponseDTO(BaseModel):
    """Response containing matched minefield alerts and formatted system prompt advisory."""

    alerts: list[MinefieldAlertDTO] = Field(default_factory=list)
    advisory_prompt: str = ""
    has_critical_alerts: bool = False
