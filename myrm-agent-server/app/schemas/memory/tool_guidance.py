"""Schemas for Tool Guidance operations and governance."""

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
