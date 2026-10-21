"""
[POS] app/schemas/agent_hierarchy.py
[INPUT] typing, pydantic
[OUTPUT] CreatorTypeLiteral, AgentProvenanceDTO, AgentHierarchyNodeDTO, AgentHierarchyTreeResponseDTO, RegisterProvenanceRequestDTO

Pydantic schemas for agent creation hierarchy, provenance tracking, and tree listing.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CreatorTypeLiteral = Literal[
    "user",
    "agent",
    "script",
    "system",
]


class AgentProvenanceDTO(BaseModel):
    """Provenance metadata describing how and by whom an agent was instantiated."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Target agent profile ID")
    creator_type: CreatorTypeLiteral = Field(..., description="Entity kind responsible for creation")
    creator_id: str = Field(..., description="Identifier of creator (user ID, parent agent ID, script name)")
    parent_agent_id: str | None = Field(default=None, description="Optional parent agent ID in hierarchy")
    created_at: float = Field(default_factory=time.time, description="Creation epoch timestamp")
    ancestry_path: list[str] = Field(default_factory=list, description="Chain of agent IDs from root ancestor to self")


class RegisterProvenanceRequestDTO(BaseModel):
    """Payload to register or update creation provenance for an agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., min_length=1, description="Target agent profile ID")
    creator_type: CreatorTypeLiteral = Field(default="user", description="Creation source kind")
    creator_id: str = Field(..., min_length=1, description="Creator ID or agent reference")
    parent_agent_id: str | None = Field(default=None, description="Parent agent ID in hierarchy")


class AgentHierarchyNodeDTO(BaseModel):
    """Tree node representing an agent within the creation hierarchy."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str = Field(..., description="Agent profile ID")
    name: str = Field(..., description="Agent display name")
    description: str = Field(default="", description="Agent description")
    avatar: str | None = Field(default=None, description="Avatar image or SVG path")
    agent_type: str = Field(default="individual", description="Agent type: individual, team, subagent")
    provenance: AgentProvenanceDTO = Field(..., description="Creation provenance details")
    depth: int = Field(ge=0, default=0, description="Nesting depth in hierarchy tree (0 = root)")
    children: list[AgentHierarchyNodeDTO] = Field(default_factory=list, description="Direct child agents created by this agent")


class AgentHierarchyTreeResponseDTO(BaseModel):
    """Collection response containing hierarchical agent forest tree."""

    model_config = ConfigDict(extra="forbid")

    roots: list[AgentHierarchyNodeDTO] = Field(default_factory=list, description="Top-level root agents")
    total_nodes: int = Field(ge=0, description="Total agent nodes across all trees")
    max_depth: int = Field(ge=0, description="Maximum tree depth in hierarchy")
