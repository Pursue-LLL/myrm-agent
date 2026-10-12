"""
[POS] app/api/security/enterprise_hipaa_compliance_router.py
[INPUT] fastapi, app.schemas.enterprise_hipaa_compliance, app.services.security.enterprise_hipaa_compliance_service
[OUTPUT] enterprise_hipaa_compliance_router
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.enterprise_hipaa_compliance import (
    BYOCompliantProviderDTO,
    ComplianceExportPackageDTO,
    EnterpriseComplianceMetricsDTO,
    ExportCompliancePackageRequestDTO,
    HipaaAuditChainEntryDTO,
    PhiScreeningRequestDTO,
    PhiScreeningResponseDTO,
    RecordAuditEventRequestDTO,
    RegisterProviderRequestDTO,
    ValidateProviderEgressRequestDTO,
    ValidateProviderEgressResponseDTO,
    VerifyChainResponseDTO,
)
from app.services.security.enterprise_hipaa_compliance_service import (
    EnterpriseHipaaComplianceService,
    get_enterprise_hipaa_compliance_service,
)

router = APIRouter(
    prefix="/enterprise-hipaa-compliance",
    tags=["Enterprise BAA / HIPAA Compliance Conduit"],
)


@router.get(
    "/providers",
    response_model=list[BYOCompliantProviderDTO],
    summary="List all registered Bring-Your-Own compliant model providers",
)
def list_compliant_providers(
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> list[BYOCompliantProviderDTO]:
    """Retrieve all verified BAA and air-gapped private model endpoints."""
    return service.list_providers()


@router.post(
    "/providers",
    response_model=BYOCompliantProviderDTO,
    summary="Register a new Bring-Your-Own compliant provider endpoint",
)
def register_compliant_provider(
    request: RegisterProviderRequestDTO,
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> BYOCompliantProviderDTO:
    """Register custom BAA-signed enterprise endpoint or private vLLM cluster."""
    return service.register_provider(request)


@router.get(
    "/providers/{provider_id}",
    response_model=BYOCompliantProviderDTO,
    summary="Fetch provider registration details by ID",
)
def get_compliant_provider(
    provider_id: str,
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> BYOCompliantProviderDTO:
    """Retrieve registration configuration and whitelist status of a provider."""
    provider = service.get_provider(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' not found")
    return provider


@router.post(
    "/audit/events",
    response_model=HipaaAuditChainEntryDTO,
    summary="Record an immutable event into the sequential SHA-256 audit ledger",
)
def record_audit_event(
    request: RecordAuditEventRequestDTO,
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> HipaaAuditChainEntryDTO:
    """Append an immutable audit entry to the cryptographic hash chain."""
    return service.record_audit_event(request)


@router.get(
    "/audit/verify",
    response_model=VerifyChainResponseDTO,
    summary="Verify unbroken cryptographic integrity of the HIPAA audit ledger",
)
def verify_audit_chain(
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> VerifyChainResponseDTO:
    """Verify unbroken SHA-256 hash chaining of all recorded audit events."""
    return service.verify_audit_chain()


@router.post(
    "/audit/export",
    response_model=ComplianceExportPackageDTO,
    summary="Export verifiable compliance package with root summary digest",
)
def export_compliance_package(
    request: ExportCompliancePackageRequestDTO,
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> ComplianceExportPackageDTO:
    """Generate verifiable proof package for healthcare enterprise auditors."""
    return service.export_compliance_package(request)


@router.post(
    "/phi/screen",
    response_model=PhiScreeningResponseDTO,
    summary="Screen and redact Protected Health Information (PHI) tokens",
)
def screen_phi_content(
    request: PhiScreeningRequestDTO,
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> PhiScreeningResponseDTO:
    """Detect and mask MRN, SSN, NPI and DOB tokens in prompts or completions."""
    return service.screen_phi(request)


@router.post(
    "/egress/validate",
    response_model=ValidateProviderEgressResponseDTO,
    summary="Validate egress to target provider and inject zero-training headers",
)
def validate_provider_egress(
    request: ValidateProviderEgressRequestDTO,
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> ValidateProviderEgressResponseDTO:
    """Gate outgoing AI API requests based on signed BAA agreements and sovereignty headers."""
    return service.validate_egress(request)


@router.get(
    "/metrics",
    response_model=EnterpriseComplianceMetricsDTO,
    summary="Get operational telemetry counters for BAA/HIPAA pipeline",
)
def get_compliance_metrics(
    service: EnterpriseHipaaComplianceService = Depends(
        get_enterprise_hipaa_compliance_service
    ),
) -> EnterpriseComplianceMetricsDTO:
    """Return aggregated telemetry metrics for compliance events."""
    return service.get_metrics()
