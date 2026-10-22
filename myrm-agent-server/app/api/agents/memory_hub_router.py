"""Agent Memory Asset Hub & Equipment Slots API Router.

[INPUT]
- CreateAssetRequest, AclUpdateRequest, EquipAssetRequest

[OUTPUT]
- MemoryAsset, AgentEquipmentSummary, list of MemoryAsset

[POS]
app/api/agents/memory_hub_router.py: REST endpoints for 4-tier cognitive asset catalog,
fine-grained ACL policy management, and game-like agent equipment loadout binding.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.services.memory.asset_hub import (
    AclScope,
    AclUpdateRequest,
    AgentEquipmentSummary,
    CreateAssetRequest,
    EquipAssetRequest,
    MemoryAsset,
    MemoryAssetType,
    memory_asset_hub_service,
)

router = APIRouter(tags=["Memory Asset Hub"])


@router.get(
    "/memory-hub/assets",
    response_model=list[MemoryAsset],
    summary="List memory assets with granular ACL security checks",
)
def list_memory_assets(
    agent_id: str | None = Query(default=None, description="Requesting agent ID for ACL enforcement"),
    asset_type: MemoryAssetType | None = Query(default=None, description="Filter by asset tier"),
    acl_scope: AclScope | None = Query(default=None, description="Filter by ACL scope"),
    project_id: str | None = Query(default=None, description="Filter by project boundary"),
) -> list[MemoryAsset]:
    """Retrieve all accessible memory assets according to caller's ACL rights."""
    return memory_asset_hub_service.list_assets(
        requesting_agent_id=agent_id,
        asset_type=asset_type,
        acl_scope=acl_scope,
        project_id=project_id,
    )


@router.post(
    "/memory-hub/assets",
    response_model=MemoryAsset,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new cognitive memory asset",
)
def create_memory_asset(
    req: CreateAssetRequest,
    agent_id: str = Query(default="system", description="Owner agent ID"),
    project_id: str = Query(default="default-project", description="Project ID"),
) -> MemoryAsset:
    """Create a new memory asset in the unified catalog."""
    return memory_asset_hub_service.create_asset(
        req=req,
        owner_agent_id=agent_id,
        project_id=project_id,
    )


@router.get(
    "/memory-hub/assets/{asset_id}",
    response_model=MemoryAsset,
    summary="Get single memory asset by ID",
)
def get_memory_asset(asset_id: str) -> MemoryAsset:
    """Retrieve details for a single memory asset."""
    asset = memory_asset_hub_service.get_asset(asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory asset '{asset_id}' not found",
        )
    return asset


@router.put(
    "/memory-hub/assets/{asset_id}/acl",
    response_model=MemoryAsset,
    summary="Update ACL policy for a memory asset",
)
def update_memory_asset_acl(
    asset_id: str,
    req: AclUpdateRequest,
    agent_id: str | None = Query(default=None, description="Caller agent ID to verify ownership"),
) -> MemoryAsset:
    """Update granular ACL scope and authorized agents list."""
    try:
        updated = memory_asset_hub_service.update_asset_acl(
            asset_id=asset_id,
            req=req,
            requesting_agent_id=agent_id,
        )
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory asset '{asset_id}' not found",
            )
        return updated
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err


@router.get(
    "/agents/{agent_id}/equipment",
    response_model=AgentEquipmentSummary,
    summary="Get current equipment loadout for an agent",
)
def get_agent_equipment(agent_id: str) -> AgentEquipmentSummary:
    """Retrieve all 4 equipment slots and their currently mounted assets."""
    return memory_asset_hub_service.get_agent_equipment(agent_id)


@router.post(
    "/agents/{agent_id}/equipment",
    response_model=AgentEquipmentSummary,
    summary="Equip a memory asset into an agent slot",
)
def equip_agent_asset(
    agent_id: str,
    req: EquipAssetRequest,
    project_id: str | None = Query(default=None, description="Project boundary for validation"),
) -> AgentEquipmentSummary:
    """Equip an asset into an equipment slot after strict ACL and type validation."""
    try:
        return memory_asset_hub_service.equip_asset(
            agent_id=agent_id,
            slot_id=req.slot_id,
            asset_id=req.asset_id,
            project_id=project_id,
        )
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.delete(
    "/agents/{agent_id}/equipment/{slot_id}",
    response_model=AgentEquipmentSummary,
    summary="Unequip asset from an agent slot",
)
def unequip_agent_asset(
    agent_id: str,
    slot_id: str,
) -> AgentEquipmentSummary:
    """Unequip whatever asset is currently in the specified slot."""
    return memory_asset_hub_service.unequip_asset(agent_id, slot_id)
