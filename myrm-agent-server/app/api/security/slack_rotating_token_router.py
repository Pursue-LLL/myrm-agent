"""API router for Slack Rotating Token Classification and Scope Inspection.

[INPUT]
- ClassifySlackTokenRequest, InspectSlackScopeRequest.

[OUTPUT]
- ClassifySlackTokenResponse, InspectSlackScopeResponse.

[POS]
- Security router mounted under /security/slack-rotating-token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.slack_rotating_token import (
    ClassifySlackTokenRequest,
    ClassifySlackTokenResponse,
    InspectSlackScopeRequest,
    InspectSlackScopeResponse,
)
from app.services.security.slack_rotating_token_service import (
    SlackRotatingTokenService,
    slack_rotating_token_service,
)

router = APIRouter(prefix="/slack-rotating-token", tags=["slack-rotating-token"])


def get_slack_rotating_token_service() -> SlackRotatingTokenService:
    """Dependency provider for SlackRotatingTokenService."""
    return slack_rotating_token_service


@router.post(
    "/classify",
    response_model=ClassifySlackTokenResponse,
    status_code=status.HTTP_200_OK,
)
async def classify_token(
    request: ClassifySlackTokenRequest,
    service: SlackRotatingTokenService = Depends(get_slack_rotating_token_service),
) -> ClassifySlackTokenResponse:
    """Classify a Slack token string or authorization header into its category and type."""
    try:
        return service.classify_token(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token classification failed: {exc}",
        ) from exc


@router.post(
    "/inspect-scopes",
    response_model=InspectSlackScopeResponse,
    status_code=status.HTTP_200_OK,
)
async def inspect_scopes(
    request: InspectSlackScopeRequest,
    service: SlackRotatingTokenService = Depends(get_slack_rotating_token_service),
) -> InspectSlackScopeResponse:
    """Inspect and extract OAuth scopes from Slack metadata according to token semantic type."""
    try:
        return service.inspect_scopes(request)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scope inspection failed: {exc}",
        ) from exc
