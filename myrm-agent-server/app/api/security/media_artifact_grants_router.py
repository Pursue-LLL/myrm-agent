"""
[POS] app/api/security/media_artifact_grants_router.py
[INPUT] fastapi, app.schemas.media_artifact_grants, app.services.security.media_artifact_grants_service
[OUTPUT] media_artifact_grants_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.media_artifact_grants import (
    EvaluateGrantRequestDTO,
    GrantEvaluationResponseDTO,
    MediaArtifactGrantMetricsDTO,
    MediaArtifactGrantResponseDTO,
    RevokeGrantRequestDTO,
    RevokeGrantResponseDTO,
)
from app.services.security.media_artifact_grants_service import (
    MediaArtifactGrantsService,
    get_media_artifact_grants_service,
)

router = APIRouter(
    prefix="/media-artifact-grants",
    tags=["Media Artifact Role-Scoped Grants"],
)


@router.post(
    "/evaluate",
    response_model=GrantEvaluationResponseDTO,
    summary="Evaluate role-scoped artifact inline render grant",
)
def evaluate_grant(
    request: EvaluateGrantRequestDTO,
    service: MediaArtifactGrantsService = Depends(get_media_artifact_grants_service),
) -> GrantEvaluationResponseDTO:
    """Evaluate whether an artifact produced within a session is authorized for inline rendering."""
    return service.evaluate_and_grant(request)


@router.post(
    "/revoke",
    response_model=RevokeGrantResponseDTO,
    summary="Revoke inline render grant",
)
def revoke_grant(
    request: RevokeGrantRequestDTO,
    service: MediaArtifactGrantsService = Depends(get_media_artifact_grants_service),
) -> RevokeGrantResponseDTO:
    """Revoke an active inline presentation grant for a session artifact."""
    return service.revoke_grant(request)


@router.get(
    "/sessions/{session_id}/artifacts/{artifact_id}",
    response_model=MediaArtifactGrantResponseDTO,
    summary="Get artifact grant record",
)
def get_grant(
    session_id: str,
    artifact_id: str,
    service: MediaArtifactGrantsService = Depends(get_media_artifact_grants_service),
) -> MediaArtifactGrantResponseDTO:
    """Fetch stored role-scoped authorization grant for an artifact."""
    grant = service.get_grant(session_id=session_id, artifact_id=artifact_id)
    if grant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Grant for artifact '{artifact_id}' in session '{session_id}' not found",
        )
    return grant


@router.get(
    "/sessions/{session_id}",
    response_model=list[MediaArtifactGrantResponseDTO],
    summary="List artifact grants for session",
)
def list_grants_for_session(
    session_id: str,
    service: MediaArtifactGrantsService = Depends(get_media_artifact_grants_service),
) -> list[MediaArtifactGrantResponseDTO]:
    """Retrieve all artifact grants issued for a session."""
    return service.list_grants_for_session(session_id=session_id)


@router.get(
    "/metrics",
    response_model=MediaArtifactGrantMetricsDTO,
    summary="Get operational metrics",
)
def get_metrics(
    service: MediaArtifactGrantsService = Depends(get_media_artifact_grants_service),
) -> MediaArtifactGrantMetricsDTO:
    """Get real-time metrics for media artifact grant evaluation."""
    return service.get_metrics()
