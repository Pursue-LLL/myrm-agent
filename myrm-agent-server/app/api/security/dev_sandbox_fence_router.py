"""FastAPI router for Zero-Production-Write Dev Sandbox and Synthetic Data Fence.

[INPUT]
- HTTP requests via FastAPI for sandbox inspection and dev mode configuration.

[OUTPUT]
- APIRouter exposing endpoints for sandbox policy inspection and alerts.

[POS]
API presentation layer for development sandbox fence governance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.dev_sandbox_fence import (
    DevPolicyResponse,
    DevViolationAlertResponse,
    InspectDevOperationRequest,
    InspectDevOperationResponse,
    RegisterSyntheticFixtureRequest,
    SetDevModeRequest,
    SyntheticFixtureResponse,
)
from app.services.security.dev_sandbox_fence_service import (
    DevSandboxFenceService,
    get_dev_sandbox_fence_service,
)

router = APIRouter(prefix="/dev-fence", tags=["dev-fence"])


@router.post(
    "/inspect",
    response_model=InspectDevOperationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate dev operation against sandbox fence rules",
)
def inspect_dev_operation(
    request: InspectDevOperationRequest,
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> InspectDevOperationResponse:
    """Evaluate SQL queries, Git branches, file writes, or DB connections for zero-production-write safety."""
    return service.inspect_operation(request)


@router.post(
    "/fixtures",
    response_model=SyntheticFixtureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register approved synthetic data fixture",
)
def register_fixture(
    request: RegisterSyntheticFixtureRequest,
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> SyntheticFixtureResponse:
    """Register an approved synthetic or masked test dataset fixture."""
    return service.register_fixture(request)


@router.get(
    "/fixtures",
    response_model=list[SyntheticFixtureResponse],
    status_code=status.HTTP_200_OK,
    summary="List available synthetic data fixtures",
)
def list_fixtures(
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> list[SyntheticFixtureResponse]:
    """Retrieve all approved synthetic test datasets."""
    return service.list_fixtures()


@router.delete(
    "/fixtures/{fixture_id}",
    status_code=status.HTTP_200_OK,
    summary="Unregister synthetic data fixture",
)
def unregister_fixture(
    fixture_id: str,
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> dict[str, bool]:
    """Delete a synthetic test dataset fixture."""
    success = service.unregister_fixture(fixture_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fixture '{fixture_id}' not found",
        )
    return {"success": True}


@router.get(
    "/violations",
    response_model=list[DevViolationAlertResponse],
    status_code=status.HTTP_200_OK,
    summary="List dev sandbox boundary violations",
)
def get_violations(
    session_id: str | None = Query(default=None),
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> list[DevViolationAlertResponse]:
    """Retrieve security violation audit logs."""
    return service.get_alerts(session_id)


@router.get(
    "/policy",
    response_model=DevPolicyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get dev sandbox fence policy",
)
def get_policy(
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> DevPolicyResponse:
    """Query current dev policy and execution environment tier."""
    return service.get_policy()


@router.post(
    "/mode",
    status_code=status.HTTP_200_OK,
    summary="Set execution mode for dev sandbox",
)
def set_mode(
    request: SetDevModeRequest,
    service: DevSandboxFenceService = Depends(get_dev_sandbox_fence_service),
) -> dict[str, str]:
    """Set execution mode: dev_isolated, readonly_research, or production_controlled."""
    try:
        new_mode = service.set_mode(request.mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid execution mode: {exc}",
        ) from exc
    return {"mode": new_mode}
