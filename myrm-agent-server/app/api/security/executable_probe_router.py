"""API router for Executable Capability Probing.

[INPUT]
- ProbeExecutableRequest.

[OUTPUT]
- ProbeExecutableResponse.

[POS]
- Security router mounted under /security/executable-probe.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.executable_probe import (
    ProbeExecutableRequest,
    ProbeExecutableResponse,
)
from app.services.security.executable_probe_service import ExecutableProbeService

router = APIRouter(prefix="/executable-probe", tags=["executable-probe"])

_default_service = ExecutableProbeService()


def get_executable_probe_service() -> ExecutableProbeService:
    """Dependency provider for ExecutableProbeService."""
    return _default_service


@router.post(
    "/probe",
    response_model=ProbeExecutableResponse,
    status_code=status.HTTP_200_OK,
    summary="Probe an executable with shell immunity and tri-state diagnostics",
)
async def probe_executable(
    request: ProbeExecutableRequest,
    service: ExecutableProbeService = Depends(get_executable_probe_service),
) -> ProbeExecutableResponse:
    """Classify executable readiness into capable, incompatible, or broken states."""
    return service.probe_executable(request)
