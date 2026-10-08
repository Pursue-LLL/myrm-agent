"""Data transfer objects for Experience Compounding and Knowledge Condensation API.

[POS]
Defines Pydantic contracts for experience registration, logarithmic reinforcement,
semantic Golden Rule condensation, and context annealing telemetry.

[INPUT]
- typing, pydantic

[OUTPUT]
- AddExperienceItemRequest, ReinforceExperienceRequest, DecondenseRuleRequest
- CompoundedExperienceItemDTO, GoldenRuleDTO, CondensationResponseDTO
- AnnealingResponseDTO, ExperienceCompoundingStatsResponse
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AddExperienceItemRequest(BaseModel):
    """Payload to register a new experience observation or preference fragment."""

    content: str = Field(min_length=1, description="Raw content of the preference or habit")
    topic: str = Field(min_length=1, description="Domain topic (e.g. coding_style, workflow, arch)")
    base_weight: float = Field(default=1.0, gt=0.0, le=5.0, description="Initial base importance weight")
    is_temporary: bool = Field(default=False, description="Whether this is a transient one-off context")
    is_pinned: bool = Field(default=False, description="Whether this item is under active lease protection")
    tags: list[str] = Field(default_factory=list, description="Categorical tags for filtering")
    item_id: str | None = Field(default=None, description="Optional explicit item identifier")


class ReinforceExperienceRequest(BaseModel):
    """Payload to record verification or adoption of an experience item."""

    item_id: str = Field(min_length=1, description="Unique identifier of the target experience item")
    adopted: bool = Field(default=True, description="Whether the suggestion was positively adopted")


class DecondenseRuleRequest(BaseModel):
    """Payload to roll back a synthesized Golden Rule into original active fragments."""

    rule_id: str = Field(min_length=1, description="Identifier of the Golden Rule to decondense")


class CompoundedExperienceItemDTO(BaseModel):
    """Data transfer representation of a compounded experience item."""

    item_id: str = Field(description="Unique experience item identifier")
    content: str = Field(description="Body content snippet")
    topic: str = Field(description="Domain topic")
    base_weight: float = Field(description="Initial base weight")
    compounded_weight: float = Field(description="Compounded weight score after reinforcement")
    hit_count: int = Field(ge=0, description="Total hit count")
    adoption_count: int = Field(ge=0, description="Total positive adoption count")
    state: str = Field(description="Lifecycle state: active, condensed_archived, cold_tiered")
    half_life_days: float = Field(gt=0.0, description="Current retention half-life in days")
    is_pinned: bool = Field(description="Whether protected by active lease")
    is_temporary: bool = Field(description="Whether transient context")
    tags: list[str] = Field(default_factory=list, description="Associated tags")


class GoldenRuleDTO(BaseModel):
    """Data transfer representation of a synthesized higher-order Golden Rule."""

    rule_id: str = Field(description="Unique Golden Rule identifier")
    topic: str = Field(description="Domain topic")
    rule_statement: str = Field(description="Synthesized canonical principle statement")
    rationale: str = Field(description="Audit explanation and lineage basis")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Aggregated confidence rating")
    source_fragment_ids: list[str] = Field(description="List of archived source fragment IDs")


class CondensationResponseDTO(BaseModel):
    """Result report from semantic condensation synthesis."""

    report_id: str = Field(description="Unique condensation run identifier")
    rules_generated: list[GoldenRuleDTO] = Field(description="List of synthesized Golden Rules")
    clusters_found: int = Field(ge=0, description="Total semantic clusters identified")
    fragments_archived: int = Field(ge=0, description="Total micro-fragments archived non-destructively")
    compression_ratio: float = Field(ge=0.0, le=1.0, description="Token compression ratio achieved")
    details: list[str] = Field(default_factory=list, description="Audit log lines")


class AnnealingResponseDTO(BaseModel):
    """Result report from obsolete context annealing decay run."""

    report_id: str = Field(description="Unique annealing execution identifier")
    inspected_count: int = Field(ge=0, description="Total active items evaluated")
    active_lease_exempt_count: int = Field(ge=0, description="Items exempted due to active leases")
    cold_tiered_count: int = Field(ge=0, description="Items demoted to cold storage tier")
    decayed_items: list[str] = Field(default_factory=list, description="Demotion activity log")


class ExperienceCompoundingStatsResponse(BaseModel):
    """Aggregated operational metrics across compounding, condensation, and cold storage."""

    total_items: int = Field(ge=0, description="Total items registered in the suite")
    active_items: int = Field(ge=0, description="Count of hot active items")
    condensed_items: int = Field(ge=0, description="Count of archived fragments absorbed by Golden Rules")
    cold_tiered_items: int = Field(ge=0, description="Count of context items sunk to cold tier")
    golden_rules_count: int = Field(ge=0, description="Count of active Golden Rules")
    average_compounded_weight: float = Field(ge=0.0, description="Mean compounded weight across all items")
