"""Schemas for Tool Guidance operations and governance.

[INPUT]
- pydantic::BaseModel (POS: Validation and serialization foundation)

[OUTPUT]
- ToolGuidanceItemDTO: Data transfer object for individual tool guidance rule
- ToolGuidanceGroupDTO: Data transfer object grouping synthesized guidelines and items by tool
- ToolGuidanceResponseDTO: Top-level API response DTO for tool guidance listing
- ToolGuidancePinRequestDTO: Request DTO for pinning/unpinning a tool rule

[POS]
Tool memory governance schema layer. Defines HTTP request and response DTOs
for tool-level behavioral rules and dynamic guidelines.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolGuidanceItemDTO(BaseModel):
    id: str
    tool_name: str
    rule_text: str
    trigger_pattern: str
    confidence: float = 1.0
    is_pinned: bool = False
    env_fingerprint: str | None = None
    agent_id: str | None = None
    source: str = "self_healing"
    hit_count: int = 1
    created_at: str
    updated_at: str


class ToolGuidanceGroupDTO(BaseModel):
    tool_name: str
    guidelines: list[str] = Field(default_factory=list)
    has_pinned: bool = False
    items: list[ToolGuidanceItemDTO] = Field(default_factory=list)


class ToolGuidanceListResponse(BaseModel):
    tools: list[ToolGuidanceGroupDTO] = Field(default_factory=list)
    total_tools: int = 0
    total_rules: int = 0


class PinGuidanceRequest(BaseModel):
    rule_id: str
    is_pinned: bool = True


class PinGuidanceResponse(BaseModel):
    rule_id: str
    is_pinned: bool
    status: str = "success"
