"""Domain types and Pydantic models for Agent Memory Asset Hub and Equipment Slots.

[INPUT] None (Pydantic and standard typing)
[OUTPUT] Pure domain types: MemoryAssetType, AclScope, MemoryAsset, EquipmentSlot, AgentEquipmentSummary.
[POS] app/services/memory/asset_hub/asset_hub_types.py
"""

from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field


class MemoryAssetType(str, Enum):
    """The four major tiers of agent memory assets."""

    CHAT_MEMORY = "chat_memory"
    SKILL = "skill"
    WIKI = "wiki"
    CODE_GRAPH = "code_graph"


class AclScope(str, Enum):
    """Granular access control scopes for memory assets."""

    PRIVATE = "private"  # Exclusive to the owner agent
    TEAM = "team"  # Shared across all agents in the workspace
    PROJECT = "project"  # Scoped strictly to the specific project/sandbox volume


class MemoryAsset(BaseModel):
    """Memory asset entity representing a reusable cognitive item."""

    id: str
    name: str
    description: str
    asset_type: MemoryAssetType
    acl_scope: AclScope
    owner_agent_id: str = "system"
    project_id: str = "default-project"
    allowed_agent_ids: list[str] = Field(default_factory=list)
    content_preview: str = ""
    tags: list[str] = Field(default_factory=list)
    size_bytes: int = 1024
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EquipmentSlot(BaseModel):
    """A slot in the agent's game-like memory equipment loadout."""

    slot_id: str
    slot_name: str
    allowed_types: list[MemoryAssetType]
    equipped_asset_id: str | None = None
    equipped_asset: MemoryAsset | None = None


class AgentEquipmentSummary(BaseModel):
    """Summary of all equipped memory assets for an agent."""

    agent_id: str
    slots: list[EquipmentSlot]
    total_equipped: int
    max_slots: int = 4


class EquipAssetRequest(BaseModel):
    """Request payload to equip an asset into a slot."""

    slot_id: str
    asset_id: str


class UnequipAssetRequest(BaseModel):
    """Request payload to unequip an asset from a slot."""

    slot_id: str


class CreateAssetRequest(BaseModel):
    """Request payload to register a new memory asset."""

    name: str
    description: str
    asset_type: MemoryAssetType
    acl_scope: AclScope = AclScope.TEAM
    content_preview: str = ""
    tags: list[str] = Field(default_factory=list)
    allowed_agent_ids: list[str] = Field(default_factory=list)


class AclUpdateRequest(BaseModel):
    """Request payload to modify an asset's ACL policy."""

    acl_scope: AclScope
    allowed_agent_ids: list[str] = Field(default_factory=list)
