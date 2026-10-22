"""Agent Memory Asset Hub & Equipment Slots subpackage.

[INPUT] None (Facade re-exports)
[OUTPUT] Domain types and singleton MemoryAssetHubService instance.
[POS] app/services/memory/asset_hub/__init__.py
"""

from app.services.memory.asset_hub.asset_hub_types import (
    AclScope,
    AclUpdateRequest,
    AgentEquipmentSummary,
    CreateAssetRequest,
    EquipAssetRequest,
    EquipmentSlot,
    MemoryAsset,
    MemoryAssetType,
    UnequipAssetRequest,
)
from app.services.memory.asset_hub.asset_hub_service import (
    MemoryAssetHubService,
    memory_asset_hub_service,
)

__all__ = [
    "AclScope",
    "AclUpdateRequest",
    "AgentEquipmentSummary",
    "CreateAssetRequest",
    "EquipAssetRequest",
    "EquipmentSlot",
    "MemoryAsset",
    "MemoryAssetType",
    "UnequipAssetRequest",
    "MemoryAssetHubService",
    "memory_asset_hub_service",
]
