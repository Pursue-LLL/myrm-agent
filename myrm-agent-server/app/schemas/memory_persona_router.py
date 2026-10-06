"""
[POS] app/schemas/memory_persona_router.py
[INPUT] pydantic
[OUTPUT] PersonaFacetDTO, RoutePersonaContextRequestDTO, RoutePersonaContextResponseDTO

Pydantic DTOs for On-Demand Persona Skill and Anti-Pollution Context Router.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PersonaFacetDTO(BaseModel):
    """Decoupled user identity and style preference facet representation."""

    model_config = ConfigDict(extra="forbid")

    facet_id: str = Field(..., description="Unique persona facet identifier")
    name: str = Field(..., description="Display name of persona style")
    tone_guidance: str = Field(
        ..., description="Specific guidelines governing tone and communication"
    )
    sample_excerpts: list[str] = Field(
        default_factory=list, description="Exemplar sample excerpts"
    )
    target_intents: list[str] = Field(
        default_factory=list, description="Target intent categories for activation"
    )
    is_default: bool = Field(
        default=False, description="Whether this facet is default fallback"
    )
    estimated_tokens: int = Field(
        default=150, ge=0, description="Estimated token footprint of this facet"
    )


class RoutePersonaContextRequestDTO(BaseModel):
    """Payload to route query and select or suppress persona facets."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="User turn prompt to evaluate")
    facets: list[PersonaFacetDTO] = Field(
        default_factory=list, description="Candidate persona facets to route"
    )
    explicit_facet_id: str | None = Field(
        default=None, description="Optional explicitly selected facet identifier"
    )


class RoutePersonaContextResponseDTO(BaseModel):
    """Outcome of intent-aware persona suppression and context injection."""

    model_config = ConfigDict(extra="forbid")

    is_suppressed: bool = Field(
        ..., description="Whether persona tokens were completely suppressed"
    )
    intent_category: str = Field(
        ..., description="Classified intent category (technical/creative/general)"
    )
    active_facets: list[str] = Field(
        default_factory=list, description="IDs of activated persona facets"
    )
    injected_content: str = Field(
        default="", description="Rendered persona guidance block (empty if suppressed)"
    )
    tokens_saved_estimate: int = Field(
        ..., ge=0, description="Estimated token budget saved by suppression"
    )
    decision_reason: str = Field(
        ..., description="Human-readable decision explanation"
    )
