"""Credential Stdin Pipelining & Process Leakage Shield Service.

[INPUT]
- AnalyzeCommandLineRequest, PipelineCommandRequest, SanitizeDisplayCommandRequest.

[OUTPUT]
- ProcessLeakageAnalysisDto, PipelinedCommandDto, SanitizedDisplayResponse.

[POS]
- Server security service. Wraps harness CommandLineCredentialInspector and
  CredentialStdinPipeliningEngine to safeguard process table secrets.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.credential_shield import (
    CommandLineCredentialInspector,
    CredentialStdinPipeliningEngine,
    PipelinedCommandSpec,
    ProcessLeakageAnalysis,
)

from app.schemas.credential_shield import (
    AnalyzeCommandLineRequest,
    PipelineCommandRequest,
    PipelinedCommandDto,
    ProcessLeakageAnalysisDto,
    SanitizedDisplayResponse,
    SanitizeDisplayCommandRequest,
)

logger = logging.getLogger(__name__)


def _to_analysis_dto(analysis: ProcessLeakageAnalysis) -> ProcessLeakageAnalysisDto:
    return ProcessLeakageAnalysisDto(
        is_safe_for_process_table=analysis.is_safe_for_process_table,
        risk_level=analysis.risk_level.value,
        detected_leaks=list(analysis.detected_leaks),
        suggested_rewritten_command=analysis.suggested_rewritten_command,
        audit_notes=analysis.audit_notes,
    )


def _to_pipelined_dto(spec: PipelinedCommandSpec) -> PipelinedCommandDto:
    return PipelinedCommandDto(
        original_command=spec.original_command,
        sanitized_argv=list(spec.sanitized_argv),
        has_stdin_payload=len(spec.stdin_payload) > 0,
        transport_mode=spec.transport_mode.value,
        sanitized_display_cmd=spec.sanitized_display_cmd,
        detected_secret_patterns=list(spec.detected_secret_patterns),
    )


class CredentialShieldService:
    """Service governing command line credential inspection and stdin pipelining."""

    def __init__(
        self,
        inspector: type[CommandLineCredentialInspector] = CommandLineCredentialInspector,
        engine: type[CredentialStdinPipeliningEngine] = CredentialStdinPipeliningEngine,
    ) -> None:
        self._inspector = inspector
        self._engine = engine

    def analyze_command(self, req: AnalyzeCommandLineRequest) -> ProcessLeakageAnalysisDto:
        """Inspect a command line for plain-text credential leaks visible in OS process tables."""
        res = self._inspector.inspect(req.command)
        return _to_analysis_dto(res)

    def pipeline_command(self, req: PipelineCommandRequest) -> PipelinedCommandDto:
        """Transform a command into an immune stdin-pipelined execution specification."""
        spec = self._engine.pipeline_command(req.command)
        return _to_pipelined_dto(spec)

    def sanitize_display(self, req: SanitizeDisplayCommandRequest) -> SanitizedDisplayResponse:
        """Redact credentials from a command string for safe logging and display."""
        sanitized = self._inspector.sanitize_display(req.command)
        return SanitizedDisplayResponse(sanitized_command=sanitized)


_service_instance: CredentialShieldService | None = None


def get_credential_shield_service() -> CredentialShieldService:
    """Obtain or initialize singleton CredentialShieldService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = CredentialShieldService()
    return _service_instance
