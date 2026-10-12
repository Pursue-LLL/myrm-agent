"""API router for Workspace File Access Boundary Guard & Actual Path Link Resolver.

[INPUT]
- ResolvePathRequest, EvaluateAccessRequest, ParseMarkdownLinksRequest, DesktopRevealVerifyRequest.

[OUTPUT]
- Endpoints for resolving link paths, evaluating action permissions, parsing chat Markdown links,
  and verifying safe desktop file reveals.

[POS]
- Server API. Mounted under /api/v1/security/workspace-boundary.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from app.schemas.workspace_boundary import (
    DesktopRevealVerifyRequest,
    DesktopRevealVerifyResponse,
    EvaluateAccessRequest,
    ParseMarkdownLinksRequest,
    ParseMarkdownLinksResponse,
    PathResolutionDto,
    ResolvePathRequest,
)
from app.services.security.workspace_boundary_service import (
    get_workspace_boundary_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspace-boundary", tags=["workspace-boundary"])


@router.post("/resolve", response_model=PathResolutionDto)
def resolve_path(request: ResolvePathRequest) -> PathResolutionDto:
    """Resolve a file link or URI to its on-disk physical location and test boundary containment."""
    service = get_workspace_boundary_service()
    return service.resolve_path(request)


@router.post("/evaluate", response_model=PathResolutionDto)
def evaluate_access(request: EvaluateAccessRequest) -> PathResolutionDto:
    """Evaluate whether an agent or desktop action (launch, reveal, read) is authorized for a file."""
    service = get_workspace_boundary_service()
    return service.evaluate_access(request)


@router.post("/parse-markdown", response_model=ParseMarkdownLinksResponse)
def parse_markdown_links(request: ParseMarkdownLinksRequest) -> ParseMarkdownLinksResponse:
    """Extract all file links from a Markdown message and evaluate their physical resolution."""
    service = get_workspace_boundary_service()
    return service.parse_markdown_links(request)


@router.post("/desktop-reveal-verify", response_model=DesktopRevealVerifyResponse)
def verify_desktop_reveal(request: DesktopRevealVerifyRequest) -> DesktopRevealVerifyResponse:
    """Verify and sanitize a file path prior to triggering OS file explorer reveal."""
    service = get_workspace_boundary_service()
    return service.verify_desktop_reveal(request)
