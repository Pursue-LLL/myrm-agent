"""Pydantic schemas for the experience injection suite (skill load, subagent spawn and pre-write check).

[INPUT]
- pydantic::{BaseModel, ConfigDict, Field} (POS: validated request and response models)

[OUTPUT]
- InjectSkillExperienceRequest, InjectSkillExperienceResponseDTO: experience enrichment of a loaded skill body
- InjectSubagentExperienceRequest, InjectSubagentExperienceResponseDTO: experience enrichment of a subagent task prompt
- PreWriteCheckRequest, PreWriteCheckResponseDTO: pre-write context and verdict

[POS]
API contracts of experience injection, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InjectSkillExperienceRequest(BaseModel):
    """Request payload to inject procedure experience into a skill markdown body."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str = Field(..., description="Target skill identifier name")
    skill_content: str = Field(..., description="Raw markdown content of the skill")
    agent_id: str | None = Field(default=None, description="Optional agent namespace isolation identifier")


class InjectSkillExperienceResponseDTO(BaseModel):
    """Response payload returning enriched skill content with injected experiences."""

    model_config = ConfigDict(extra="forbid")

    skill_name: str
    status: str
    injected_count: int
    enriched_content: str
    injected_entry_ids: list[str] = Field(default_factory=list)


class InjectSubagentExperienceRequest(BaseModel):
    """Request payload to enrich subagent task prompt with relevant procedure experiences."""

    model_config = ConfigDict(extra="forbid")

    subagent_role: str = Field(..., description="Target subagent role description")
    task_prompt: str = Field(..., description="Base prompt for delegated subtask")
    agent_id: str | None = Field(default=None, description="Optional agent namespace isolation identifier")


class InjectSubagentExperienceResponseDTO(BaseModel):
    """Response payload returning enriched subagent prompt."""

    model_config = ConfigDict(extra="forbid")

    subagent_role: str
    status: str
    injected_count: int
    enriched_prompt: str
    injected_entry_ids: list[str] = Field(default_factory=list)


class PreWriteCheckRequest(BaseModel):
    """Request payload to evaluate planned mutating tool call against immutable boundaries."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str = Field(..., description="Mutating tool name (e.g., write_file, edit_file)")
    tool_args: dict[str, str] = Field(default_factory=dict, description="Arguments passed to the tool")
    current_context: str = Field(..., description="Current agent reasoning or execution context")
    agent_id: str | None = Field(default=None, description="Optional agent namespace isolation identifier")


class PreWriteCheckResponseDTO(BaseModel):
    """Response payload detailing pre-write guard evaluation and rollback recommendation."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: str
    rollback_required: bool
    enriched_context: str
    injected_entry_ids: list[str] = Field(default_factory=list)
