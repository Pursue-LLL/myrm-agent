"""
[POS] app/api/security/case_variant_scrubber_router.py
[INPUT] app.schemas.case_variant_scrubber, app.services.security.case_variant_scrubber_service
[OUTPUT] router

FastAPI router for Case-Variant Credential Scrubbing & Declarative OAuth PKCE Provider Seam Suite.
Exposes endpoints to deep-scrub child process environment variables, detect injection vectors,
and manage declarative OAuth 2.0 PKCE authentication flows.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.case_variant_scrubber import (
    DetectInjectionsRequest,
    DetectInjectionsResponse,
    ExchangePKCETokenRequest,
    ExchangePKCETokenResponse,
    InitiatePKCEFlowRequest,
    InitiatePKCEFlowResponse,
    OAuthProviderManifestResponse,
    RegisterOAuthProviderRequest,
    RegisterOAuthProviderResponse,
    ScrubberSuiteMetricsResponse,
    ScrubEnvironmentRequest,
    ScrubEnvironmentResponse,
)
from app.services.security.case_variant_scrubber_service import (
    CaseVariantScrubberService,
    get_case_variant_scrubber_service,
)

router = APIRouter(
    prefix="/case-variant-scrubber",
    tags=["Case-Variant Credential Scrubbing & Declarative OAuth PKCE"],
)


@router.post(
    "/scrub-env",
    response_model=ScrubEnvironmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Deeply scrub environment dictionary against case variants and delimiter bypasses",
)
def scrub_environment(
    request: ScrubEnvironmentRequest,
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> ScrubEnvironmentResponse:
    """Normalize environment keys to lowercase and drop or mask matching credentials."""
    return service.scrub_environment(request)


@router.post(
    "/detect-injections",
    response_model=DetectInjectionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Probe environment dictionary for intentional case-variant credential injections",
)
def detect_injections(
    request: DetectInjectionsRequest,
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> DetectInjectionsResponse:
    """Detect whether environment variables contain mixed-case credential variants."""
    return service.detect_injections(request)


@router.post(
    "/pkce/initiate",
    response_model=InitiatePKCEFlowResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate OAuth 2.0 PKCE challenge flow and generate browser authorization URL",
)
def initiate_pkce_flow(
    request: InitiatePKCEFlowRequest,
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> InitiatePKCEFlowResponse:
    """Generate RFC 7636 code challenge and browser redirect URL."""
    try:
        return service.initiate_pkce_flow(request)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to initiate PKCE flow: {err}",
        ) from err


@router.post(
    "/pkce/exchange",
    response_model=ExchangePKCETokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate PKCE challenge state and prepare token exchange payload",
)
def exchange_pkce_token(
    request: ExchangePKCETokenRequest,
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> ExchangePKCETokenResponse:
    """Validate anti-CSRF state token and return code verifier for upstream token exchange."""
    try:
        return service.exchange_pkce_token(request)
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"PKCE token exchange validation failed: {err}",
        ) from err


@router.get(
    "/providers",
    response_model=list[OAuthProviderManifestResponse],
    summary="List registered declarative OAuth model provider manifests",
)
def list_providers(
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> list[OAuthProviderManifestResponse]:
    """Retrieve all active declarative OAuth provider specifications."""
    return service.list_providers()


@router.post(
    "/providers",
    response_model=RegisterOAuthProviderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new declarative external model provider manifest",
)
def register_provider(
    request: RegisterOAuthProviderRequest,
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> RegisterOAuthProviderResponse:
    """Register third-party OAuth provider for seamless PKCE browser authentication."""
    return service.register_provider(request)


@router.get(
    "/metrics",
    response_model=ScrubberSuiteMetricsResponse,
    summary="Get cumulative operational metrics for scrubber and PKCE suite",
)
def get_metrics(
    service: CaseVariantScrubberService = Depends(get_case_variant_scrubber_service),
) -> ScrubberSuiteMetricsResponse:
    """Inspect total envs scrubbed, credentials intercepted, and PKCE sessions."""
    return service.get_metrics()
