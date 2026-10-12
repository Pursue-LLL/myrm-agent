"""Security Audit Explicit Coverage & Replayable Repair Bundle Service.

[INPUT]
- InitializeAuditSessionRequest, RecordFindingRequest, AttachRepairBundleRequest.

[OUTPUT]
- ExplicitAuditCoverageReportDto, AuditFindingDto, ReplayableRepairBundleDto.

[POS]
- Server security service. Wraps harness AuditCoverageEngine to enforce
  application model contracts, adversarial challenges, and replayable repair bundles.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.audit_coverage import (
    ApplicationModel,
    AuditCoverageEngine,
    AuditFinding,
    ChallengeVerdict,
    CoverageCategory,
    CoverageScopeItem,
    CoverageStatus,
    ExplicitAuditCoverageReport,
    FindingSeverity,
    RepairPatch,
    ReplayableRepairBundle,
    VerificationTier,
)

from app.schemas.audit_coverage import (
    ApplicationModelDto,
    AttachRepairBundleRequest,
    AuditFindingDto,
    CoverageScopeItemDto,
    ExplicitAuditCoverageReportDto,
    InitializeAuditSessionRequest,
    RecordFindingRequest,
    RepairPatchDto,
    ReplayableRepairBundleDto,
)

logger = logging.getLogger(__name__)


def _to_domain_model(dto: ApplicationModelDto) -> ApplicationModel:
    return ApplicationModel(
        name=dto.name,
        tech_stack=tuple(dto.tech_stack),
        entrypoints=tuple(dto.entrypoints),
        trust_boundaries=tuple(dto.trust_boundaries),
        data_flows=tuple(dto.data_flows),
        supported_finding_categories=tuple(dto.supported_finding_categories),
    )


def _to_dto_model(domain: ApplicationModel) -> ApplicationModelDto:
    return ApplicationModelDto(
        name=domain.name,
        tech_stack=list(domain.tech_stack),
        entrypoints=list(domain.entrypoints),
        trust_boundaries=list(domain.trust_boundaries),
        data_flows=list(domain.data_flows),
        supported_finding_categories=list(domain.supported_finding_categories),
    )


def _to_domain_scope(dto: CoverageScopeItemDto) -> CoverageScopeItem:
    return CoverageScopeItem(
        category=CoverageCategory(dto.category),
        status=CoverageStatus(dto.status),
        audit_surface=dto.audit_surface,
        coverage_percentage=dto.coverage_percentage,
        uncovered_reason=dto.uncovered_reason,
    )


def _to_dto_scope(domain: CoverageScopeItem) -> CoverageScopeItemDto:
    return CoverageScopeItemDto(
        category=domain.category.value,
        status=domain.status.value,
        audit_surface=domain.audit_surface,
        coverage_percentage=domain.coverage_percentage,
        uncovered_reason=domain.uncovered_reason,
    )


def _to_domain_finding(dto: AuditFindingDto) -> AuditFinding:
    return AuditFinding(
        finding_id=dto.finding_id,
        category=dto.category,
        severity=FindingSeverity(dto.severity),
        title=dto.title,
        description=dto.description,
        application_model_ref=dto.application_model_ref,
        evidence=dto.evidence,
        challenge_status=ChallengeVerdict(dto.challenge_status),
        challenge_notes=dto.challenge_notes,
        verification_tier=VerificationTier(dto.verification_tier),
    )


def _to_dto_finding(domain: AuditFinding) -> AuditFindingDto:
    return AuditFindingDto(
        finding_id=domain.finding_id,
        category=domain.category,
        severity=domain.severity.value,
        title=domain.title,
        description=domain.description,
        application_model_ref=domain.application_model_ref,
        evidence=domain.evidence,
        challenge_status=domain.challenge_status.value,
        challenge_notes=domain.challenge_notes,
        verification_tier=domain.verification_tier.value,
    )


def _to_dto_bundle(domain: ReplayableRepairBundle) -> ReplayableRepairBundleDto:
    patches_dto = [
        RepairPatchDto(
            file_path=p.file_path,
            target_checksum=p.target_checksum,
            diff_content=p.diff_content,
            replay_command=p.replay_command,
        )
        for p in domain.patches
    ]
    return ReplayableRepairBundleDto(
        bundle_id=domain.bundle_id,
        finding_id=domain.finding_id,
        patches=patches_dto,
        replay_script=domain.replay_script,
        checksum=domain.checksum,
        is_verified=domain.is_verified,
    )


def _to_dto_report(domain: ExplicitAuditCoverageReport) -> ExplicitAuditCoverageReportDto:
    return ExplicitAuditCoverageReportDto(
        audit_id=domain.audit_id,
        application_model=_to_dto_model(domain.application_model),
        scopes=[_to_dto_scope(s) for s in domain.scopes],
        findings=[_to_dto_finding(f) for f in domain.findings],
        repair_bundles=[_to_dto_bundle(b) for b in domain.repair_bundles],
        overall_coverage_percentage=domain.overall_coverage_percentage,
    )


class AuditCoverageService:
    """Service governing explicit security coverage disclosure and replayable repair bundles."""

    def __init__(self) -> None:
        default_model = ApplicationModel(
            name="DefaultApplicationService",
            tech_stack=("Python", "FastAPI"),
            entrypoints=("/api/v1/health",),
            trust_boundaries=("Ingress -> Service",),
            data_flows=("Internal REST calls",),
            supported_finding_categories=(
                "AUTH_ACCESS_CONTROL",
                "INPUT_VALIDATION_INJECTION",
                "SECRET_LEAKAGE",
            ),
        )
        self._engine = AuditCoverageEngine(application_model=default_model)

    def initialize_session(
        self, req: InitializeAuditSessionRequest
    ) -> ExplicitAuditCoverageReportDto:
        """Initialize a new audit session with declared application model and scopes."""
        domain_model = _to_domain_model(req.application_model)
        self._engine = AuditCoverageEngine(application_model=domain_model)
        for s in req.scopes:
            self._engine.register_scope(_to_domain_scope(s))
        return _to_dto_report(self._engine.generate_coverage_report())

    def register_scopes(self, scopes: list[CoverageScopeItemDto]) -> None:
        """Register coverage scope disclosures into the active session."""
        for s in scopes:
            self._engine.register_scope(_to_domain_scope(s))

    def record_finding(self, req: RecordFindingRequest) -> AuditFindingDto:
        """Record and adversarially challenge a security finding."""
        domain_finding = _to_domain_finding(req.finding)
        processed = self._engine.record_finding(
            domain_finding,
            codebase_context=req.codebase_context,
            auto_challenge=req.auto_challenge,
        )
        return _to_dto_finding(processed)

    def attach_repair_bundle(
        self, req: AttachRepairBundleRequest
    ) -> ReplayableRepairBundleDto:
        """Generate and attach a replayable repair bundle to an audit finding."""
        patches = [
            RepairPatch(
                file_path=p.file_path,
                target_checksum=p.target_checksum,
                diff_content=p.diff_content,
                replay_command=p.replay_command,
            )
            for p in req.patches
        ]
        bundle = self._engine.attach_repair_bundle(
            finding_id=req.finding_id,
            patches=patches,
            replay_script=req.replay_script,
            verify_immediately=req.verify_immediately,
        )
        return _to_dto_bundle(bundle)

    def get_coverage_report(self) -> ExplicitAuditCoverageReportDto:
        """Retrieve full audit report with explicit coverage metrics and findings."""
        report = self._engine.generate_coverage_report()
        return _to_dto_report(report)


_service_instance: AuditCoverageService | None = None


def get_audit_coverage_service() -> AuditCoverageService:
    """Obtain or initialize singleton AuditCoverageService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = AuditCoverageService()
    return _service_instance
