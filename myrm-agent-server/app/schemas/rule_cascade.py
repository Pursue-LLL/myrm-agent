# [POS]: app/schemas/rule_cascade.py
# [INPUT]: None (Pydantic models)
# [OUTPUT]: RegisterRuleRequest, RegisterRuleResponse, QueryCascadedRulesRequest, CascadedRuleSetDTO, PreFilterEvidenceRequest, PreFilteredEvidenceResponse

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FiveDimEvidenceMetadataDTO(BaseModel):
    """DTO representing 5-dimensional evidence metadata."""

    model_config = ConfigDict(extra="forbid")

    scope: str = Field(..., description="Scope kind: global, organization, workspace, directory, file")
    scope_path: str = Field(..., description="Scope path, e.g. /workspace/packages/billing")
    source: str = Field(..., description="Source kind: user_explicit, tool_verified, agent_inferred")
    source_authority: float = Field(default=1.0, ge=0.0, le=1.0, description="Authority score (0.0 to 1.0)")
    created_at: str | None = Field(default=None, description="ISO 8601 created timestamp")
    half_life_days: float = Field(default=30.0, gt=0.0, description="Half-life decay in days")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Baseline confidence")
    permission: str = Field(default="public", description="Permission level: public, workspace_internal, confidential_admin")


class DeterministicRuleEntryDTO(BaseModel):
    """DTO representing a deterministic engineering constraint rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    rule_content: str
    metadata: FiveDimEvidenceMetadataDTO
    is_enforced: bool = True


class RegisterRuleRequest(BaseModel):
    """Request payload to register a deterministic engineering rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    title: str
    rule_content: str
    metadata: FiveDimEvidenceMetadataDTO
    is_enforced: bool = True


class RegisterRuleResponse(BaseModel):
    """Response returned upon successfully registering a rule."""

    model_config = ConfigDict(extra="forbid")

    is_success: bool = True
    rule_id: str
    registered_rule: DeterministicRuleEntryDTO


class QueryCascadedRulesRequest(BaseModel):
    """Request payload to query hierarchical rules cascaded along a target path."""

    model_config = ConfigDict(extra="forbid")

    target_path: str = Field(..., description="Target file or directory path in workspace")


class CascadedRuleSetDTO(BaseModel):
    """Consolidated set of cascaded rules resolved for a target path."""

    model_config = ConfigDict(extra="forbid")

    target_path: str
    inherited_rules: list[DeterministicRuleEntryDTO]
    effective_rules_count: int
    sources_breakdown: dict[str, int]


class PreFilterEvidenceRequest(BaseModel):
    """Request payload to filter candidate evidence against 5-dimensional boundary spec."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[DeterministicRuleEntryDTO]
    allowed_scopes: list[str] | None = None
    scope_path_prefix: str | None = None
    min_authority: float = Field(default=0.0, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    required_permission: str | None = None
    max_decay_age_days: float | None = None


class PreFilteredEvidenceResponse(BaseModel):
    """Response containing pre-filtered evidence items and rejection audit breakdown."""

    model_config = ConfigDict(extra="forbid")

    passed_items: list[DeterministicRuleEntryDTO]
    total_evaluated: int
    passed_count: int
    rejection_reasons: dict[str, int]
