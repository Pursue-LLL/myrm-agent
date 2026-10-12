"""Unit test for LicenseComplianceService.

[INPUT]
- EvaluateLicenseRequest, RegisterAssetRequest.

[OUTPUT]
- Verified behavior for license compliance service methods.

[POS]
- Server unit test layer.
"""

from __future__ import annotations

from app.schemas.license_compliance import (
    EvaluateLicenseRequest,
    RegisterAssetRequest,
)
from app.services.security.license_compliance_service import (
    LicenseComplianceService,
)


def test_service_evaluate_asset_rules() -> None:
    service = LicenseComplianceService()

    # Permissive license
    res_mit = service.evaluate_asset(
        EvaluateLicenseRequest(
            asset_id="skill-test",
            declared_license="MIT",
            environment="CLOUD_COMMERCIAL",
        )
    )
    assert res_mit.decision == "ALLOWED"
    assert res_mit.detected_license.risk_tier == "PERMISSIVE"

    # Strong copyleft in cloud
    res_agpl = service.evaluate_asset(
        EvaluateLicenseRequest(
            asset_id="skill-agpl",
            declared_license="AGPL-3.0",
            environment="CLOUD_COMMERCIAL",
        )
    )
    assert res_agpl.decision == "BLOCKED_COPYLEFT_RESTRICTION"
    assert res_agpl.can_override is True

    # Strong copyleft with override
    res_agpl_override = service.evaluate_asset(
        EvaluateLicenseRequest(
            asset_id="skill-agpl",
            declared_license="AGPL-3.0",
            environment="CLOUD_COMMERCIAL",
            allow_override=True,
        )
    )
    assert res_agpl_override.decision == "WARNING_PROCEED"


def test_service_inventory_lifecycle_and_sbom() -> None:
    service = LicenseComplianceService()

    # Register assets
    reg1 = service.register_asset(
        RegisterAssetRequest(
            asset_id="tool-bsd",
            asset_type="mcp_server",
            declared_license="BSD-3-Clause",
            package_url="pkg:generic/tool-bsd@1.0",
        )
    )
    assert reg1.asset_id == "tool-bsd"
    assert reg1.detected_license.spdx_id == "BSD-3-Clause"

    reg2 = service.register_asset(
        RegisterAssetRequest(
            asset_id="tool-gpl",
            asset_type="skill",
            declared_license="GPL-3.0",
        )
    )
    assert reg2.detected_license.risk_tier == "STRONG_COPYLEFT"

    # List
    assets = service.list_assets()
    assert len(assets) == 2

    # Summary
    summary = service.get_inventory_summary(environment="CLOUD_COMMERCIAL")
    assert summary.total_assets == 2
    assert summary.has_blocking_violations is True

    # Export CycloneDX
    sbom = service.export_cyclonedx_sbom()
    assert len(sbom) == 2
    gpl_entry = next(s for s in sbom if s.bom_ref == "tool-gpl")
    assert gpl_entry.copyleft == "true"

    # Unregister
    assert service.unregister_asset("tool-bsd") is True
    assert service.unregister_asset("nonexistent") is False
    assert len(service.list_assets()) == 1
