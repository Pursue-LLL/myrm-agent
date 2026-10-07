"""Pydantic V2 DTO schemas for external agent skill bridge and memory gateway.

[POS]
app/schemas/external_skill_bridge.py
Provides data exchange contracts for configuring external agent memory skills
and executing low-latency memory queries and contributions from external tools.

[INPUT]
- typing: List, Optional, Literal
- pydantic: BaseModel, ConfigDict, Field

[OUTPUT]
- ExternalAgentTargetDTO, ExternalTargetsListResponse, InstallSkillBridgeRequest
- InstallSkillBridgeResponse, UninstallSkillBridgeRequest, UninstallSkillBridgeResponse
- ExternalMemoryQueryRequest, ExternalMemoryHitDTO, ExternalMemoryQueryResponse
- ExternalMemoryContributeRequest, ExternalMemoryContributeResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExternalAgentTargetDTO(BaseModel):
    """Metadata describing an external agent integration target."""

    model_config = ConfigDict(extra="forbid")

    agent_type: str = Field(..., description="Unique agent identifier (cursor, claude_code, etc.).")
    name: str = Field(..., description="Human-readable agent display name.")
    target_path: str = Field(..., description="Resolved local filesystem path for bridge rules.")
    is_installed: bool = Field(..., description="Whether the bridge delimiter block is installed.")
    has_conflict: bool = Field(..., description="Whether conflicting legacy memory directives exist.")
    conflicts: list[str] = Field(default_factory=list, description="List of detected conflicting rules.")
    is_read_only: bool = Field(default=False, description="Whether bridge is configured in read-only mode.")


class ExternalTargetsListResponse(BaseModel):
    """Response containing all supported external agent targets."""

    model_config = ConfigDict(extra="forbid")

    targets: list[ExternalAgentTargetDTO] = Field(
        default_factory=list,
        description="Supported agent targets and their status.",
    )
    total_supported: int = Field(..., description="Count of supported agents.")


class InstallSkillBridgeRequest(BaseModel):
    """Request payload to install or update a memory bridge skill."""

    model_config = ConfigDict(extra="forbid")

    agent_type: str = Field(..., description="Agent type (cursor, claude_code, codex, hermes, openclaw).")
    workspace_root: str | None = Field(default=None, description="Target workspace directory.")
    global_config: bool = Field(default=False, description="Install into global user directory if true.")
    api_base_url: str = Field(default="http://127.0.0.1:8000", description="Base URL of Myrm server.")
    custom_target_path: str | None = Field(default=None, description="Custom explicit destination file.")
    read_only: bool = Field(default=False, description="If true, generate read-only instructions.")
    max_recalled_facts: int = Field(default=8, ge=1, le=50, description="Max facts to query by default.")


class InstallSkillBridgeResponse(BaseModel):
    """Response returned upon installing or updating a skill bridge."""

    model_config = ConfigDict(extra="forbid")

    agent_type: str = Field(..., description="Agent type processed.")
    target_path: str = Field(..., description="Filesystem path where bridge was written.")
    action: str = Field(..., description="Action outcome: created, updated, or unchanged.")
    success: bool = Field(..., description="Whether installation succeeded.")
    details: str = Field(default="", description="Human-readable execution details or warnings.")
    error: str | None = Field(default=None, description="Error message if failed.")


class UninstallSkillBridgeRequest(BaseModel):
    """Request payload to uninstall a memory bridge skill."""

    model_config = ConfigDict(extra="forbid")

    agent_type: str = Field(..., description="Agent type to uninstall.")
    workspace_root: str | None = Field(default=None, description="Workspace directory.")
    global_config: bool = Field(default=False, description="Uninstall from global user directory.")
    custom_target_path: str | None = Field(default=None, description="Custom target file.")


class UninstallSkillBridgeResponse(BaseModel):
    """Response returned upon uninstalling a skill bridge."""

    model_config = ConfigDict(extra="forbid")

    agent_type: str = Field(..., description="Agent type processed.")
    target_path: str = Field(..., description="Filesystem path processed.")
    removed: bool = Field(..., description="Whether delimiters were found and removed.")
    file_deleted: bool = Field(..., description="Whether an otherwise empty file was deleted.")
    success: bool = Field(..., description="Whether uninstallation succeeded.")
    details: str = Field(default="", description="Execution details.")
    error: str | None = Field(default=None, description="Error message if failed.")


class ExternalMemoryQueryRequest(BaseModel):
    """Fast recall query from external agent tools."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Search keyword or semantic query text.")
    limit: int = Field(default=8, ge=1, le=50, description="Maximum items to return.")
    category: str | None = Field(default=None, description="Optional category filter.")


class ExternalMemoryHitDTO(BaseModel):
    """Individual retrieved memory hit for external agents."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique memory item ID.")
    text: str = Field(..., description="Memory factual statement or rule.")
    category: str = Field(default="preference", description="Fact category.")
    score: float = Field(default=1.0, description="Relevance score.")
    created_at: str = Field(..., description="ISO 8601 creation timestamp.")


class ExternalMemoryQueryResponse(BaseModel):
    """Fast recall response returned to external agent."""

    model_config = ConfigDict(extra="forbid")

    hits: list[ExternalMemoryHitDTO] = Field(default_factory=list, description="Retrieved memory items.")
    total_hits: int = Field(..., description="Total matching hits count.")
    took_ms: float = Field(..., description="Query processing duration in milliseconds.")


class ExternalMemoryContributeRequest(BaseModel):
    """Payload to save newly extracted memory fact from external agent."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=2, max_length=2000, description="Extracted memory content.")
    category: str = Field(default="preference", description="Category: preference, constraint, etc.")
    confidence: float = Field(default=0.9, ge=0.0, le=1.0, description="Fact extraction confidence.")


class ExternalMemoryContributeResponse(BaseModel):
    """Response confirming or rejecting external fact contribution."""

    model_config = ConfigDict(extra="forbid")

    accepted: bool = Field(..., description="Whether fact passed security scrutiny and was saved.")
    fact_id: str | None = Field(default=None, description="Assigned memory ID if accepted.")
    redacted_text: str = Field(default="", description="Sanitized fact text after secret redaction.")
    reason: str | None = Field(default=None, description="Reason if contribution was rejected.")
