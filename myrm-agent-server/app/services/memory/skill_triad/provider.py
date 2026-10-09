"""Service provider for memory skill triad and physical scope isolation.

[POS]
Adapter layer between FastAPI controllers and the core harness skill_triad engine.
Converts domain entities into Pydantic V2 DTOs with strictly typed, zero-Any contracts.

[INPUT]
- app.schemas.skill_triad
- myrm_agent_harness.toolkits.memory.skill_triad.facade
- myrm_agent_harness.toolkits.memory.skill_triad.models

[OUTPUT]
- MemorySkillTriadProvider
- get_memory_skill_triad_provider
"""

from __future__ import annotations

import time

from myrm_agent_harness.toolkits.memory.skill_triad.facade import (
    MemorySkillTriadFacade,
    get_memory_skill_triad_facade,
)
from myrm_agent_harness.toolkits.memory.skill_triad.models import (
    DegradedStateReport,
    IntegrationSeams,
    MachineCliEnvelope,
    ScopeCoordinates,
    ScopePartitionInfo,
    SurveyFinding,
)

from app.schemas.skill_triad import (
    CliEnvelopeResponse,
    DegradedReportResponse,
    DeleteScopeRequest,
    DeleteScopeResponse,
    FormatCliEnvelopeRequest,
    ProviderAssessRequest,
    ProviderDegradedInfoDTO,
    ResolveScopeRequest,
    ScopeCoordinatesDTO,
    ScopePartitionResponse,
    ValidateSurveyRequest,
    ValidateSurveyResponse,
    VerifySeamsRequest,
    VerifySeamsResponse,
)


class MemorySkillTriadProvider:
    """Service adapter exposing physical scope partitioning and skill triad verification."""

    def __init__(self, facade: MemorySkillTriadFacade | None = None) -> None:
        self._facade: MemorySkillTriadFacade = facade or get_memory_skill_triad_facade()

    @staticmethod
    def _to_domain_coordinates(dto: ScopeCoordinatesDTO) -> ScopeCoordinates:
        return ScopeCoordinates(
            tenant_id=dto.tenant_id,
            workspace_id=dto.workspace_id,
            agent_id=dto.agent_id,
            session_id=dto.session_id,
        )

    @staticmethod
    def _to_dto_coordinates(coords: ScopeCoordinates) -> ScopeCoordinatesDTO:
        return ScopeCoordinatesDTO(
            tenant_id=coords.tenant_id,
            workspace_id=coords.workspace_id,
            agent_id=coords.agent_id,
            session_id=coords.session_id,
        )

    def resolve_scope(self, request: ResolveScopeRequest) -> ScopePartitionResponse:
        """Derives physical filesystem directory and dedicated SQLite path."""
        domain_coords = self._to_domain_coordinates(request.coordinates)
        partition: ScopePartitionInfo = self._facade.resolve_scope(domain_coords)
        return ScopePartitionResponse(
            coordinates=self._to_dto_coordinates(partition.coordinates),
            namespace_hash=partition.namespace_hash,
            partition_dir=partition.partition_dir,
            sqlite_path=partition.sqlite_path,
            is_isolated=partition.is_isolated,
        )

    def delete_scope(self, request: DeleteScopeRequest) -> DeleteScopeResponse:
        """Atomically purges physical directory for a specific scope."""
        domain_coords = self._to_domain_coordinates(request.coordinates)
        deleted: bool = self._facade.delete_scope(domain_coords)
        ns_hash = self._facade._partition_engine.compute_namespace_hash(domain_coords)
        return DeleteScopeResponse(deleted=deleted, namespace_hash=ns_hash)

    def assess_providers(self, request: ProviderAssessRequest) -> DegradedReportResponse:
        """Inspects provider configuration and returns visible degradation report."""
        report: DegradedStateReport = self._facade.assess_providers(
            request.configured_providers, strict_mode=request.strict_mode
        )
        return DegradedReportResponse(
            overall_status=report.overall_status.value,
            providers=[
                ProviderDegradedInfoDTO(
                    provider_type=p.provider_type,
                    configured_vendor=p.configured_vendor,
                    active_vendor=p.active_vendor,
                    is_degraded=p.is_degraded,
                    degradation_reason=p.degradation_reason,
                )
                for p in report.providers
            ],
            strict_mode=report.strict_mode,
            summary=report.summary,
        )

    def format_cli_envelope(self, request: FormatCliEnvelopeRequest) -> CliEnvelopeResponse:
        """Wraps operation outcome into standardized machine CLI envelope."""
        domain_coords = self._to_domain_coordinates(request.scope)
        start_time = time.perf_counter()
        envelope: MachineCliEnvelope = self._facade.wrap_cli_success(
            command=request.command,
            start_time_s=start_time,
            scope=domain_coords,
            payload=request.payload,
            agent_mode=request.agent_mode,
        )
        return CliEnvelopeResponse(
            status=envelope.status,
            command=envelope.command,
            duration_ms=envelope.duration_ms,
            scope=envelope.scope,
            payload=envelope.payload,
            error_code=envelope.error_code,
            error_message=envelope.error_message,
            exit_code=envelope.exit_code,
            auto_confirmed=envelope.auto_confirmed,
        )

    def validate_survey(self, request: ValidateSurveyRequest) -> ValidateSurveyResponse:
        """Validates pre-integration repository survey findings."""
        finding = SurveyFinding(
            message_assembly_site=request.finding.message_assembly_site,
            identity_binding=request.finding.identity_binding,
            installed_provider=request.finding.installed_provider,
            write_hook_seam=request.finding.write_hook_seam,
            is_ready_for_wiring=request.finding.is_ready_for_wiring,
        )
        is_valid, issues = self._facade.validate_survey(finding)
        return ValidateSurveyResponse(is_valid=is_valid, issues=issues)

    def verify_seams(self, request: VerifySeamsRequest) -> VerifySeamsResponse:
        """Verifies read and write seams and pre-flight roundtrip test status."""
        seams = IntegrationSeams(
            read_seam_configured=request.read_seam_configured,
            write_seam_configured=request.write_seam_configured,
            token_budget=request.token_budget,
            roundtrip_test_passed=request.roundtrip_test_passed,
        )
        is_verified, msg = self._facade.verify_seams(seams)
        return VerifySeamsResponse(is_verified=is_verified, message=msg)


_PROVIDER_INSTANCE: MemorySkillTriadProvider | None = None


def get_memory_skill_triad_provider() -> MemorySkillTriadProvider:
    """Returns singleton instance of MemorySkillTriadProvider."""
    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is None:
        _PROVIDER_INSTANCE = MemorySkillTriadProvider()
    return _PROVIDER_INSTANCE
