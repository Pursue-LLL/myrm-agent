"""API Router for Managed Permission Template Presets, Session Checkpoint Rollback, and Connectors Hub.

[POS] app/api/security/managed_permission_rollback_router.py
[INPUT] fastapi, app.schemas.managed_permission_rollback, app.services.security.managed_permission_rollback_service
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.managed_permission_rollback import (
    ComplianceDriftCheckRequest,
    ComplianceDriftResponse,
    CreateSessionCheckpointRequest,
    ManagedConnectorMetaDTO,
    RegisterConnectorRequest,
    RolePermissionPolicyDTO,
    RollbackSessionCheckpointRequest,
    RollbackSessionCheckpointResponse,
    SessionCheckpointDTO,
)
from app.services.security.managed_permission_rollback_service import (
    ManagedPermissionRollbackService,
    get_managed_permission_rollback_service,
)

router = APIRouter(
    prefix="/managed-permissions",
    tags=["Security - Managed Permission Presets, Checkpoint Rollback & Connectors Hub"],
)


@router.get(
    "/templates",
    response_model=list[RolePermissionPolicyDTO],
    status_code=status.HTTP_200_OK,
    summary="List all canonical enterprise permission template presets",
)
def list_templates_endpoint(
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> list[RolePermissionPolicyDTO]:
    """Retrieve canonical enterprise permission presets: Auditor, Safe Collaborator, Full-Stack, Ops."""
    return service.list_presets()


@router.get(
    "/templates/{role}",
    response_model=RolePermissionPolicyDTO,
    status_code=status.HTTP_200_OK,
    summary="Get canonical enterprise permission template by role",
)
def get_template_endpoint(
    role: str,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> RolePermissionPolicyDTO:
    """Retrieve specific canonical enterprise permission policy."""
    try:
        return service.get_preset(role.upper())
    except (KeyError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template preset for role '{role}' not found.",
        ) from err


@router.post(
    "/templates/drift-check",
    response_model=ComplianceDriftResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate compliance drift between active agent rules and baseline template",
)
def drift_check_endpoint(
    request: ComplianceDriftCheckRequest,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> ComplianceDriftResponse:
    """Compare active agent permissions against designated template and report deviations."""
    try:
        return service.check_compliance_drift(request)
    except (KeyError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role or enforcement rule: {err}",
        ) from err


@router.post(
    "/checkpoints/create",
    response_model=SessionCheckpointDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Capture an immutable atomic session checkpoint",
)
def create_checkpoint_endpoint(
    request: CreateSessionCheckpointRequest,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> SessionCheckpointDTO:
    """Capture snapshot of workspace files and short-term conversational memory."""
    try:
        return service.create_checkpoint(request)
    except (KeyError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create checkpoint: {err}",
        ) from err


@router.get(
    "/checkpoints/{session_id}",
    response_model=list[SessionCheckpointDTO],
    status_code=status.HTTP_200_OK,
    summary="List all checkpoints recorded for a session",
)
def list_checkpoints_endpoint(
    session_id: str,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> list[SessionCheckpointDTO]:
    """Retrieve chronological checkpoint timeline for the specified session."""
    return service.list_checkpoints(session_id)


@router.post(
    "/checkpoints/rollback",
    response_model=RollbackSessionCheckpointResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically roll back workspace and memory to a historical checkpoint",
)
def rollback_checkpoint_endpoint(
    request: RollbackSessionCheckpointRequest,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> RollbackSessionCheckpointResponse:
    """Restore file state and conversational memory back to the targeted checkpoint."""
    try:
        return service.rollback_checkpoint(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/connectors/register",
    response_model=ManagedConnectorMetaDTO,
    status_code=status.HTTP_200_OK,
    summary="Register or renew an external ecosystem connector",
)
def register_connector_endpoint(
    request: RegisterConnectorRequest,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> ManagedConnectorMetaDTO:
    """Register or update an ecosystem connector (Discord, GitHub, Slack, Notion, Jira, Feishu)."""
    try:
        return service.register_connector(request)
    except (KeyError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid connector channel: {err}",
        ) from err


@router.post(
    "/connectors/{connector_id}/heartbeat",
    response_model=ManagedConnectorMetaDTO,
    status_code=status.HTTP_200_OK,
    summary="Record heartbeat and check health of an ecosystem connector",
)
def connector_heartbeat_endpoint(
    connector_id: str,
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> ManagedConnectorMetaDTO:
    """Ping connector heartbeat and re-verify expiration posture."""
    result = service.record_connector_heartbeat(connector_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector '{connector_id}' not found.",
        )
    return result


@router.get(
    "/connectors",
    response_model=list[ManagedConnectorMetaDTO],
    status_code=status.HTTP_200_OK,
    summary="List all registered managed ecosystem connectors",
)
def list_connectors_endpoint(
    service: ManagedPermissionRollbackService = Depends(
        get_managed_permission_rollback_service
    ),
) -> list[ManagedConnectorMetaDTO]:
    """List managed ecosystem connector hub statuses."""
    return service.list_connectors()
