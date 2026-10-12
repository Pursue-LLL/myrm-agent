"""Agent Egress Telemetry Scraper & Enterprise DLP Service.

[INPUT]
- ValidateEgressPolicyRequest, ScanDependenciesRequest, ScanProjectRequest.

[OUTPUT]
- DLPScanResultDto, list[TelemetrySignatureDto].

[POS]
- Server security service. Wraps harness EgressSecurityPolicyValidator to protect
  private prompt and contextual tokens from leaking to third-party telemetry domains.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.egress_dlp import (
    DLPScanResult,
    EgressRule,
    EgressSecurityPolicyValidator,
    TelemetrySignature,
    TelemetrySignatureRegistry,
)

from app.schemas.egress_dlp import (
    DLPScanResultDto,
    EgressRuleDto,
    ScanDependenciesRequest,
    ScanProjectRequest,
    TelemetrySignatureDto,
    ValidateEgressPolicyRequest,
)

logger = logging.getLogger(__name__)


def _to_signature_dto(sig: TelemetrySignature) -> TelemetrySignatureDto:
    return TelemetrySignatureDto(
        target_domain=sig.target_domain,
        framework_name=sig.framework_name,
        risk_level=sig.risk_level.value,
        description=sig.description,
    )


def _to_rule_dto(rule: EgressRule) -> EgressRuleDto:
    return EgressRuleDto(
        destination=rule.destination,
        port=rule.port,
        protocol=rule.protocol,
        description=rule.description,
    )


def _to_result_dto(res: DLPScanResult) -> DLPScanResultDto:
    return DLPScanResultDto(
        is_safe=res.is_safe,
        verdict=res.verdict.value,
        detected_signatures=[_to_signature_dto(s) for s in res.detected_signatures],
        detected_dependencies=list(res.detected_dependencies),
        offending_rules=[_to_rule_dto(r) for r in res.offending_rules],
        audit_trail=res.audit_trail,
    )


class EgressDlpService:
    """Service governing egress traffic inspection and telemetry leak detection."""

    def __init__(self, validator: EgressSecurityPolicyValidator | None = None) -> None:
        self._validator = validator or EgressSecurityPolicyValidator()

    def validate_egress_rules(self, req: ValidateEgressPolicyRequest) -> DLPScanResultDto:
        """Validate declared egress rules against known telemetry signatures and evasion patterns."""
        domain_rules = [
            EgressRule(
                destination=r.destination,
                port=r.port,
                protocol=r.protocol,
                description=r.description,
            )
            for r in req.rules
        ]
        exceptions = set(req.allowed_exceptions)
        res = self._validator.validate_egress_rules(domain_rules, allowed_exceptions=exceptions)
        return _to_result_dto(res)

    def scan_dependencies(self, req: ScanDependenciesRequest) -> DLPScanResultDto:
        """Scan dependency file contents (requirements.txt, etc.) for telemetry SDK libraries."""
        res = self._validator.scan_dependencies(req.manifest_content)
        return _to_result_dto(res)

    def scan_project(self, req: ScanProjectRequest) -> DLPScanResultDto:
        """Scan project codebase and dependency files for prohibited telemetry tracking."""
        res = self._validator.scan_codebase_telemetry(req.project_dir)
        return _to_result_dto(res)

    def list_signatures(self) -> list[TelemetrySignatureDto]:
        """List all pre-compiled third-party telemetry domain signatures."""
        return [_to_signature_dto(s) for s in TelemetrySignatureRegistry.list_signatures()]


_service_instance: EgressDlpService | None = None


def get_egress_dlp_service() -> EgressDlpService:
    """Obtain or initialize singleton EgressDlpService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = EgressDlpService()
    return _service_instance
