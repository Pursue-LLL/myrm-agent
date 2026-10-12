"""License Compliance & Copyleft Gating Service.

[INPUT]
- EvaluateLicenseRequest, RegisterAssetRequest.

[OUTPUT]
- EvaluateLicenseResponse, AssetLicenseDescriptorDto, LicenseInventorySummaryDto, CycloneDxLicenseRecordDto.

[POS]
- Server security service. Wraps harness SpdxLicenseRegistry, LicenseComplianceGate,
  and LicenseInventoryLedger to provide licensing compliance enforcement across API endpoints.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.license_compliance import (
    AssetLicenseDescriptor,
    DeploymentEnvironment,
    LicenseComplianceGate,
    LicenseComplianceVerdict,
    LicenseInventoryLedger,
    LicenseMetadata,
    SpdxLicenseRegistry,
)

from app.schemas.license_compliance import (
    AssetLicenseDescriptorDto,
    CycloneDxLicenseRecordDto,
    EvaluateLicenseRequest,
    EvaluateLicenseResponse,
    LicenseInventorySummaryDto,
    LicenseMetadataDto,
    RegisterAssetRequest,
)

logger = logging.getLogger(__name__)


def _to_metadata_dto(meta: LicenseMetadata) -> LicenseMetadataDto:
    return LicenseMetadataDto(
        spdx_id=meta.spdx_id,
        raw_name=meta.raw_name,
        risk_tier=meta.risk_tier.value,
        is_copyleft=meta.is_copyleft,
        commercial_friendly=meta.commercial_friendly,
        description=meta.description,
    )


def _to_descriptor_dto(desc: AssetLicenseDescriptor) -> AssetLicenseDescriptorDto:
    return AssetLicenseDescriptorDto(
        asset_id=desc.asset_id,
        asset_type=desc.asset_type,
        detected_license=_to_metadata_dto(desc.detected_license),
        license_file_path=desc.license_file_path,
        package_url=desc.package_url,
    )


def _to_verdict_dto(verdict: LicenseComplianceVerdict) -> EvaluateLicenseResponse:
    return EvaluateLicenseResponse(
        decision=verdict.decision.value,
        asset_id=verdict.asset_id,
        detected_license=_to_metadata_dto(verdict.detected_license),
        environment=verdict.environment.value,
        reason=verdict.reason,
        can_override=verdict.can_override,
        audit_notes=verdict.audit_notes,
    )


class LicenseComplianceService:
    """Service governing license risk tiering, gating decisions, and inventory SBOM tracking."""

    def __init__(
        self,
        gate: LicenseComplianceGate | None = None,
        ledger: LicenseInventoryLedger | None = None,
    ) -> None:
        self._gate = gate or LicenseComplianceGate()
        self._ledger = ledger or LicenseInventoryLedger(gate=self._gate)

    def evaluate_asset(self, request: EvaluateLicenseRequest) -> EvaluateLicenseResponse:
        """Evaluate license compliance for an asset before installation."""
        try:
            env = DeploymentEnvironment(request.environment)
        except ValueError:
            env = DeploymentEnvironment.CLOUD_COMMERCIAL

        detected_license = SpdxLicenseRegistry.normalize(request.declared_license)
        descriptor = AssetLicenseDescriptor(
            asset_id=request.asset_id,
            asset_type=request.asset_type,
            detected_license=detected_license,
        )
        verdict = self._gate.evaluate(
            asset=descriptor,
            environment=env,
            allow_override=request.allow_override,
        )
        return _to_verdict_dto(verdict)

    def register_asset(self, request: RegisterAssetRequest) -> AssetLicenseDescriptorDto:
        """Scan and register a third-party asset into the active inventory ledger."""
        descriptor = self._ledger.scan_and_register_package(
            asset_id=request.asset_id,
            asset_type=request.asset_type,
            declared_license=request.declared_license,
            manifest_path=request.manifest_path,
            package_url=request.package_url,
        )
        return _to_descriptor_dto(descriptor)

    def unregister_asset(self, asset_id: str) -> bool:
        """Unregister an asset from the inventory ledger."""
        return self._ledger.unregister_asset(asset_id)

    def list_assets(self) -> list[AssetLicenseDescriptorDto]:
        """List all currently tracked third-party assets."""
        return [_to_descriptor_dto(a) for a in self._ledger.list_assets()]

    def get_inventory_summary(self, environment: str = "CLOUD_COMMERCIAL") -> LicenseInventorySummaryDto:
        """Generate aggregated compliance summary across all tracked assets."""
        try:
            env = DeploymentEnvironment(environment)
        except ValueError:
            env = DeploymentEnvironment.CLOUD_COMMERCIAL

        summary = self._ledger.summarize(environment=env)
        return LicenseInventorySummaryDto(
            total_assets=summary.total_assets,
            permissive_count=summary.permissive_count,
            weak_copyleft_count=summary.weak_copyleft_count,
            strong_copyleft_count=summary.strong_copyleft_count,
            unknown_count=summary.unknown_count,
            has_blocking_violations=summary.has_blocking_violations,
            assets=[_to_descriptor_dto(a) for a in summary.assets],
        )

    def export_cyclonedx_sbom(self) -> list[CycloneDxLicenseRecordDto]:
        """Export inventory assets formatted as CycloneDX license entries."""
        records = self._ledger.export_cyclonedx_license_records()
        output: list[CycloneDxLicenseRecordDto] = []
        for r in records:
            output.append(
                CycloneDxLicenseRecordDto(
                    bom_ref=r["bom-ref"],
                    asset_type=r["type"],
                    license_id=r["license_id"],
                    license_name=r["license_name"],
                    risk_tier=r["risk_tier"],
                    copyleft=r["copyleft"],
                    commercial_friendly=r["commercial_friendly"],
                    purl=r.get("purl"),
                )
            )
        return output


_service_instance: LicenseComplianceService | None = None


def get_license_compliance_service() -> LicenseComplianceService:
    """Obtain or initialize singleton LicenseComplianceService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = LicenseComplianceService()
    return _service_instance
