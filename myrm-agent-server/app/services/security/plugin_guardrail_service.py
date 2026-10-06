"""Service layer for External Plugin Guardrail Auditing and Migration Doctor.

[INPUT]
- PluginStaticAuditor and PluginMigrationDoctor components.

[OUTPUT]
- PluginGuardrailService, get_plugin_guardrail_service.

[POS]
- app.services.security.plugin_guardrail_service
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.plugin_guardrail_auditor import (
    AuditFinding,
    CapabilityScope,
    MigrationDiagnosticItem,
    MigrationDoctorReport,
    PluginAuditReport,
    PluginManifest,
    PluginMigrationDoctor,
    PluginStaticAuditor,
)

from app.schemas.plugin_guardrail import (
    AuditFindingModel,
    MigrationDiagnoseRequest,
    MigrationDiagnosticItemModel,
    MigrationDoctorReportResponse,
    MigrationExecuteRequest,
    MigrationExecuteResponse,
    PluginAuditReportResponse,
    PluginAuditRequest,
)

logger = logging.getLogger(__name__)


def _to_finding_model(f: AuditFinding) -> AuditFindingModel:
    return AuditFindingModel(
        severity=f.severity,
        rule_id=f.rule_id,
        description=f.description,
        file_path=f.file_path,
        line_number=f.line_number,
    )


def _to_audit_report_response(rep: PluginAuditReport) -> PluginAuditReportResponse:
    return PluginAuditReportResponse(
        plugin_id=rep.plugin_id,
        safety_rating=rep.safety_rating.value,
        is_install_allowed=rep.is_install_allowed,
        findings=[_to_finding_model(f) for f in rep.findings],
        scanned_files_count=rep.scanned_files_count,
        audit_timestamp=rep.audit_timestamp,
    )


def _to_diagnostic_model(d: MigrationDiagnosticItem) -> MigrationDiagnosticItemModel:
    return MigrationDiagnosticItemModel(
        target=d.target,
        status=d.status,
        details=d.details,
        remediation_available=d.remediation_available,
    )


def _to_doctor_response(
    plugin_id: str, rep: MigrationDoctorReport
) -> MigrationDoctorReportResponse:
    return MigrationDoctorReportResponse(
        plugin_id=plugin_id,
        is_migration_ready=rep.is_migration_ready,
        diagnostics=[_to_diagnostic_model(d) for d in rep.diagnostics],
        auto_remediated_count=rep.auto_remediated_count,
        notes=rep.notes,
    )


class PluginGuardrailService:
    """Manages static plugin security auditing and zero-loss migration doctor execution."""

    def __init__(
        self,
        auditor: PluginStaticAuditor | None = None,
        doctor: PluginMigrationDoctor | None = None,
    ) -> None:
        self._auditor = auditor or PluginStaticAuditor()
        self._doctor = doctor or PluginMigrationDoctor()
        self._audit_history: list[PluginAuditReport] = []

    def audit_plugin(self, req: PluginAuditRequest) -> PluginAuditReportResponse:
        """Run static AST and capability scoping audit against external plugin code."""
        # Convert declared scope strings to enum instances safely
        scopes: list[CapabilityScope] = []
        for s in req.manifest.declared_scopes:
            try:
                scopes.append(CapabilityScope(s.upper()))
            except ValueError:
                continue

        manifest = PluginManifest(
            plugin_id=req.manifest.plugin_id,
            name=req.manifest.name,
            version=req.manifest.version,
            author=req.manifest.author,
            entrypoint=req.manifest.entrypoint,
            declared_scopes=scopes,
            allowed_egress_hosts=req.manifest.allowed_egress_hosts,
            required_env_keys=req.manifest.required_env_keys,
        )

        report = self._auditor.audit_code(manifest, req.code_files)
        self._audit_history.append(report)

        logger.info(
            "Audited plugin %s: rating=%s, allowed=%s, findings=%d",
            report.plugin_id,
            report.safety_rating.value,
            report.is_install_allowed,
            len(report.findings),
        )
        return _to_audit_report_response(report)

    def diagnose_migration(
        self, req: MigrationDiagnoseRequest
    ) -> MigrationDoctorReportResponse:
        """Diagnose legacy plugin configurations, env variables, and memory vectors."""
        report = self._doctor.diagnose(
            legacy_config=req.legacy_config,
            legacy_env=req.legacy_env,
            memory_records_count=req.memory_records_count,
        )
        return _to_doctor_response(req.plugin_id, report)

    def execute_migration(self, req: MigrationExecuteRequest) -> MigrationExecuteResponse:
        """Execute automated zero-loss migration adaptation for plugin state."""
        mod_config, mod_env, logs = self._doctor.execute_migration(
            plugin_id=req.plugin_id,
            legacy_config=req.legacy_config,
            legacy_env=req.legacy_env,
        )
        logger.info("Executed zero-loss migration for plugin %s: %d steps", req.plugin_id, len(logs))
        return MigrationExecuteResponse(
            plugin_id=req.plugin_id,
            modernized_config=mod_config,
            modernized_env=mod_env,
            migration_logs=logs,
        )

    def get_audit_history(self, limit: int = 50) -> list[PluginAuditReportResponse]:
        """Fetch historical audit reports."""
        if limit <= 0:
            return [_to_audit_report_response(r) for r in self._audit_history]
        return [_to_audit_report_response(r) for r in self._audit_history[-limit:]]


_service_instance: PluginGuardrailService | None = None


def get_plugin_guardrail_service() -> PluginGuardrailService:
    """Singleton getter for PluginGuardrailService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PluginGuardrailService()
    return _service_instance
