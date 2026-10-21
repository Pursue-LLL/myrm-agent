"""FastAPI endpoints for Heterogeneous External Agent Adapter and Subagent Bundle Manager."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.agent.sub_agents.external_bundle import (
    ConcurrencyLimitExceededError,
    ExternalBundleNotFoundError,
    ExternalBundleSecurityViolationError,
)

from app.schemas.external_bundle import (
    BatchDispatchRequestDTO,
    BatchDispatchResultDTO,
    BundleCatalogResponseDTO,
    ExternalBundleProfileSpecDTO,
    ProbeBundleResponseDTO,
    SingleDispatchRequestDTO,
    SubagentInstanceRecordDTO,
    TerminateInstanceRequestDTO,
    TerminateInstanceResponseDTO,
)
from app.services.agent.external_bundle_service import (
    ExternalBundleService,
    get_external_bundle_service,
)

router = APIRouter(prefix="/agents/external-bundles", tags=["external-bundles"])


@router.get(
    "/bundles",
    response_model=BundleCatalogResponseDTO,
    summary="List all registered external agent profile bundles",
)
def list_bundles(
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> BundleCatalogResponseDTO:
    """Retrieve catalog of containerized and CLI external agent bundles (e.g. Claude Code, Codex)."""
    return service.list_bundles()


@router.get(
    "/bundles/{bundle_id}",
    response_model=ExternalBundleProfileSpecDTO,
    summary="Get single external agent bundle specification",
)
def get_bundle(
    bundle_id: str,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> ExternalBundleProfileSpecDTO:
    """Retrieve bundle specification by bundle ID."""
    try:
        return service.get_bundle(bundle_id)
    except ExternalBundleNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/bundles/{bundle_id}/probe",
    response_model=ProbeBundleResponseDTO,
    summary="Probe host environment for bundle executable binary",
)
def probe_bundle(
    bundle_id: str,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> ProbeBundleResponseDTO:
    """Probe host environment PATH to detect whether the external agent CLI is installed."""
    try:
        return service.probe_bundle(bundle_id)
    except ExternalBundleNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.post(
    "/sessions/{session_id}/dispatch-single",
    response_model=SubagentInstanceRecordDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Dispatch a single external subagent instance asynchronously",
)
def dispatch_single(
    session_id: str,
    req: SingleDispatchRequestDTO,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> SubagentInstanceRecordDTO:
    """Dispatch an external subagent without holding global backend mutexes."""
    try:
        return service.dispatch_single(session_id=session_id, req=req)
    except ExternalBundleNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExternalBundleSecurityViolationError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except ConcurrencyLimitExceededError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(err),
        ) from err


@router.post(
    "/sessions/{session_id}/dispatch-batch",
    response_model=BatchDispatchResultDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Concurrently dispatch multiple external subagent instances in parallel",
)
async def dispatch_batch(
    session_id: str,
    req: BatchDispatchRequestDTO,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> BatchDispatchResultDTO:
    """Launch multiple subagents simultaneously (e.g. 2 Codex + 1 Claude Code)."""
    try:
        return await service.dispatch_batch(session_id=session_id, req=req)
    except ExternalBundleNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ExternalBundleSecurityViolationError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(err),
        ) from err
    except ConcurrencyLimitExceededError as err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(err),
        ) from err


@router.get(
    "/sessions/{session_id}/instances",
    response_model=List[SubagentInstanceRecordDTO],
    summary="List all external subagent instances for session",
)
def list_instances(
    session_id: str,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> List[SubagentInstanceRecordDTO]:
    """Retrieve list of all dispatched external subagents in this session."""
    return service.list_instances(session_id=session_id)


@router.get(
    "/sessions/{session_id}/instances/{instance_id}",
    response_model=SubagentInstanceRecordDTO,
    summary="Get single external subagent telemetry and outputs",
)
def get_instance(
    session_id: str,
    instance_id: str,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> SubagentInstanceRecordDTO:
    """Retrieve full telemetry, stdout stream, and artifacts for an instance."""
    inst = service.get_subagent_instance(instance_id)
    if not inst:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Instance '{instance_id}' not found in session '{session_id}'.",
        )
    return inst


@router.post(
    "/sessions/{session_id}/instances/{instance_id}/terminate",
    response_model=TerminateInstanceResponseDTO,
    summary="Terminate an active external subagent instance",
)
def terminate_instance(
    session_id: str,
    instance_id: str,
    req: TerminateInstanceRequestDTO,
    service: ExternalBundleService = Depends(get_external_bundle_service),
) -> TerminateInstanceResponseDTO:
    """Halt an external subagent instance immediately and mark as terminated."""
    try:
        return service.terminate_instance(instance_id=instance_id, reason=req.reason)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
