"""FastAPI router for Compound Shell Risk Interceptor and Edge Auxiliary Suite.

[INPUT]
- app.schemas.compound_shell_risk::{InspectCommandRequest, ScreenCommandRequest, GenerateTitleRequest, CompactProfileRequest}
- app.services.security.compound_shell_risk_service::{CompoundShellRiskService}

[OUTPUT]
- router: APIRouter for compound shell risk inspection, command screening, title generation, and profile compaction.

[POS]
app/api/security router exposing compound shell security screening and edge utilities.
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.compound_shell_risk import (
    CommandScreeningResponse,
    CompactProfileRequest,
    CompoundCheckResponse,
    GenerateTitleRequest,
    InspectCommandRequest,
    ProfileCompactionResponse,
    ScreenCommandRequest,
    TitleGenerationResponse,
)
from app.services.security.compound_shell_risk_service import (
    CompoundShellRiskService,
)

router = APIRouter(
    prefix="/compound-shell-risk",
    tags=["Compound Shell Risk Security"],
)


@router.post(
    "/inspect",
    response_model=CompoundCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect shell command for compound control operators and destructive payloads",
)
def inspect_command(
    request: InspectCommandRequest,
) -> CompoundCheckResponse:
    """Inspect shell command structure and apply baseline compound rules."""
    service = CompoundShellRiskService.get_instance()
    return service.inspect_command(request)


@router.post(
    "/screen",
    response_model=CommandScreeningResponse,
    status_code=status.HTTP_200_OK,
    summary="Pre-screen command risk on edge in milliseconds",
)
def screen_command(
    request: ScreenCommandRequest,
) -> CommandScreeningResponse:
    """Perform low-latency command risk screening."""
    service = CompoundShellRiskService.get_instance()
    return service.screen_command(request)


@router.post(
    "/title",
    response_model=TitleGenerationResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate session title and tags locally without cloud LLM overhead",
)
def generate_title(
    request: GenerateTitleRequest,
) -> TitleGenerationResponse:
    """Extract session title and tags from first turn text."""
    service = CompoundShellRiskService.get_instance()
    return service.generate_title(request)


@router.post(
    "/profile",
    response_model=ProfileCompactionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract and compact user tech preferences with 100% local privacy",
)
def compact_profile(
    request: CompactProfileRequest,
) -> ProfileCompactionResponse:
    """Compact user profile memory locally."""
    service = CompoundShellRiskService.get_instance()
    return service.compact_profile(request)
