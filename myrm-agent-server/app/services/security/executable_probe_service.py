"""Service layer for Executable Capability Probing.

[INPUT]
- ProbeExecutableRequest DTO.

[OUTPUT]
- ProbeExecutableResponse DTO.

[POS]
- Server service encapsulating Claude-Mem #4167 shell-immune executable probing.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.executable_probe import (
    ExecutableProbeResult,
    ExecutableProbeRunner,
    ProbeOptions,
)

from app.schemas.executable_probe import (
    ExecutableProbeStatusDto,
    ProbeExecutableRequest,
    ProbeExecutableResponse,
)

logger = logging.getLogger(__name__)


class ExecutableProbeService:
    """Service providing shell-free executable testing and tri-state compatibility analysis."""

    def __init__(self, runner: ExecutableProbeRunner | None = None) -> None:
        self._runner = runner or ExecutableProbeRunner()

    def probe_executable(
        self, request: ProbeExecutableRequest
    ) -> ProbeExecutableResponse:
        """Probe an executable candidate, distinguishing capable, incompatible, and broken states."""
        options = ProbeOptions(
            timeout_sec=request.timeout_sec,
            warm_up_retry=request.warm_up_retry,
        )

        res: ExecutableProbeResult = self._runner.probe_executable(
            candidate=request.candidate_path,
            capability_flags=request.capability_flags,
            version_flag=request.version_flag,
            options=options,
        )

        return ProbeExecutableResponse(
            candidate_path=res.candidate_path,
            status=ExecutableProbeStatusDto(res.status.value),
            version=res.version,
            detail=res.detail,
            launch_failed=res.launch_failed,
            is_capable=res.is_capable,
        )
