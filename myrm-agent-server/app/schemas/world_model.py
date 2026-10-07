"""Pydantic V2 DTO schemas for L3 World Model macro memory and environment sync.

[POS]
app/schemas/world_model.py
Provides typed request and response contracts for macro world model querying,
workspace environment syncing, and dimension updates.

[INPUT]
- pydantic: BaseModel, ConfigDict, Field

[OUTPUT]
- RuntimeInfoDTO, WorldModelFieldsDTO, WorldModelQueryRequest, WorldModelQueryResponse
- WorldModelSyncRequest, WorldModelSyncResponse, WorldModelUpdateRequest, WorldModelUpdateResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RuntimeInfoDTO(BaseModel):
    """Detected language toolchain or runtime specification."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Runtime name, e.g. Python, Node.js.")
    version: str = Field(..., description="Detected version string.")
    package_manager: str = Field(..., description="Package manager, e.g. uv, poetry, pnpm.")
    key_dependencies: list[str] = Field(default_factory=list, description="Key discovered dependencies.")


class WorldModelFieldsDTO(BaseModel):
    """The four canonical dimensions of L3 World Model."""

    model_config = ConfigDict(extra="forbid")

    general_rules: str = Field(default="", description="Global governance and safety constraints.")
    project_environment: str = Field(default="", description="Runtime environment baseline.")
    project_contract: str = Field(default="", description="Architecture contract and layer topology.")
    domain_knowledge: str = Field(default="", description="Core domain models and business standards.")


class WorldModelQueryRequest(BaseModel):
    """Request payload for one-stop macro context retrieval."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(default="default", description="Target project scope identifier.")
    workspace_root: str | None = Field(default=None, description="Optional workspace directory to auto-sync.")


class WorldModelQueryResponse(BaseModel):
    """Response returning assembled macro context ready for System Prompt injection."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier.")
    version: int = Field(..., description="Optimistic entity version.")
    rendered_markdown: str = Field(..., description="Assembled markdown block encased in delimiters.")
    field_breakdown: dict[str, str] = Field(default_factory=dict, description="Dimension-by-dimension text.")
    token_estimate: int = Field(..., description="Estimated token count.")
    has_active_constraints: bool = Field(..., description="Whether any active constraints were loaded.")


class WorldModelSyncRequest(BaseModel):
    """Request to probe local workspace environment and sync into world model."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Target project identifier.")
    workspace_root: str = Field(..., min_length=1, description="Local filesystem path of target workspace.")


class WorldModelSyncResponse(BaseModel):
    """Response reporting results of workspace environment detection."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier.")
    version: int = Field(..., description="Updated version after sync.")
    detected_runtimes: list[RuntimeInfoDTO] = Field(default_factory=list, description="Discovered toolchains.")
    config_markers: list[str] = Field(default_factory=list, description="Discovered config files.")
    synced_at: float = Field(..., description="Epoch timestamp of sync operation.")


class WorldModelUpdateRequest(BaseModel):
    """Request to update a single macro dimension directly."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier.")
    field_name: str = Field(
        ...,
        description="One of: general_rules_and_safety_constraints, project_environment_profile, project_contract, domain_knowledge.",
    )
    content: str = Field(..., description="Textual content for this dimension.")
    source_ref: str | None = Field(default=None, description="Optional attribution source identifier.")


class WorldModelUpdateResponse(BaseModel):
    """Response acknowledging macro dimension update."""

    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(..., description="Project identifier.")
    version: int = Field(..., description="New version after update.")
    field_name: str = Field(..., description="Updated field name.")
    updated_at: float = Field(..., description="Epoch timestamp of update.")
