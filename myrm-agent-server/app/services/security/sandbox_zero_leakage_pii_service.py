"""Service implementation for Physical Sandbox Zero-Leakage Attestation and PII Firewall API.

[POS] app/services/security/sandbox_zero_leakage_pii_service.py
[INPUT] myrm_agent_harness.core.security.sandbox_zero_leakage_pii, app.schemas.sandbox_zero_leakage_pii
[OUTPUT] SandboxZeroLeakagePiiService, get_sandbox_zero_leakage_pii_service
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.sandbox_zero_leakage_pii.attestation import (
    PhysicalSandboxAttestationEngine,
)
from myrm_agent_harness.core.security.sandbox_zero_leakage_pii.pii_firewall import (
    BiDirectionalPiiFirewall,
)
from myrm_agent_harness.core.security.sandbox_zero_leakage_pii.transparency_audit import (
    OperatorTransparencyAuditor,
)
from myrm_agent_harness.core.security.sandbox_zero_leakage_pii.types import (
    AgentProfileSignature,
    ZeroLeakageAttestationProof,
)

from app.schemas.sandbox_zero_leakage_pii import (
    AgentProfileSignatureResponse,
    AuditOperatorRequest,
    AuditOperatorResponse,
    IssueAttestationRequest,
    ScanPiiRequest,
    ScanPiiResponse,
    SignProfileRequest,
    VerifyAttestationRequest,
    VerifyAttestationResponse,
    VerifyProfileRequest,
    VerifyProfileResponse,
    ZeroLeakageAttestationResponse,
)

logger = logging.getLogger(__name__)


class SandboxZeroLeakagePiiService:
    """Business service governing single-tenant attestation, bi-directional PII filtering, and 4D auditing."""

    def __init__(
        self,
        attestation_engine: PhysicalSandboxAttestationEngine | None = None,
        pii_firewall: BiDirectionalPiiFirewall | None = None,
        auditor: OperatorTransparencyAuditor | None = None,
    ) -> None:
        self._attestation_engine = attestation_engine or PhysicalSandboxAttestationEngine()
        self._pii_firewall = pii_firewall or BiDirectionalPiiFirewall()
        self._auditor = auditor or OperatorTransparencyAuditor()

    def issue_attestation(self, req: IssueAttestationRequest) -> ZeroLeakageAttestationResponse:
        """Issue cryptographic zero-cross-tenant leakage attestation proof."""
        proof = self._attestation_engine.issue_attestation(
            tenant_id=req.tenant_id,
            container_id=req.container_id,
            dedicated_volume_path=req.dedicated_volume_path,
            dedicated_database_lock=req.dedicated_database_lock,
            signer_identity=req.signer_identity,
        )
        return ZeroLeakageAttestationResponse(
            attestation_id=proof.attestation_id,
            tenant_id=proof.tenant_id,
            container_id=proof.container_id,
            dedicated_volume_path=proof.dedicated_volume_path,
            dedicated_database_lock=proof.dedicated_database_lock,
            issued_at=proof.issued_at,
            signer_identity=proof.signer_identity,
            attestation_signature=proof.attestation_signature,
        )

    def verify_attestation(self, req: VerifyAttestationRequest) -> VerifyAttestationResponse:
        """Verify authenticity of zero-leakage proof."""
        p = req.proof
        proof = ZeroLeakageAttestationProof(
            attestation_id=p.attestation_id,
            tenant_id=p.tenant_id,
            container_id=p.container_id,
            dedicated_volume_path=p.dedicated_volume_path,
            dedicated_database_lock=p.dedicated_database_lock,
            issued_at=p.issued_at,
            signer_identity=p.signer_identity,
            attestation_signature=p.attestation_signature,
        )
        is_valid = self._attestation_engine.verify_attestation(proof)
        reason = (
            "Proof signature is verified; physical single-tenant container isolation is intact."
            if is_valid
            else "Attestation signature verification failed or parameters tampered."
        )
        return VerifyAttestationResponse(is_valid=is_valid, reason=reason)

    def scan_pii(self, req: ScanPiiRequest) -> ScanPiiResponse:
        """Scan text and redact critical child, contact, and financial PII."""
        result = self._pii_firewall.scan_and_redact(req.text)
        return ScanPiiResponse(
            original_text=result.original_text,
            sanitized_text=result.sanitized_text,
            detected_categories=[c.value for c in result.detected_categories],
            redaction_count=result.redaction_count,
            contains_child_privacy_violation=result.contains_child_privacy_violation,
        )

    def audit_operator(self, req: AuditOperatorRequest) -> AuditOperatorResponse:
        """Execute 4D operator compliance and transparency audit."""
        score = self._auditor.audit_operator(
            operator_name=req.operator_name,
            base_model_id=req.base_model_id,
            data_jurisdiction=req.data_jurisdiction,
            is_codebase_public=req.is_codebase_public,
        )
        return AuditOperatorResponse(
            operator_identity_score=score.operator_identity_score,
            model_transparency_score=score.model_transparency_score,
            data_jurisdiction_score=score.data_jurisdiction_score,
            codebase_auditability_score=score.codebase_auditability_score,
            overall_score=score.overall_score,
            tier=score.tier.value,
            warnings=score.warnings,
        )

    def sign_profile(self, req: SignProfileRequest) -> AgentProfileSignatureResponse:
        """Sign agent profile using authority secret."""
        pkg = self._auditor.sign_agent_profile(
            profile_id=req.profile_id,
            author=req.author,
            model_id=req.model_id,
            system_prompt=req.system_prompt,
            is_official=req.is_official,
        )
        return AgentProfileSignatureResponse(
            profile_id=pkg.profile_id,
            author=pkg.author,
            model_id=pkg.model_id,
            system_prompt_hash=pkg.system_prompt_hash,
            signed_at=pkg.signed_at,
            signature=pkg.signature,
            is_official_verified=pkg.is_official_verified,
        )

    def verify_profile(self, req: VerifyProfileRequest) -> VerifyProfileResponse:
        """Verify authenticity of signed agent profile package."""
        p = req.profile
        pkg = AgentProfileSignature(
            profile_id=p.profile_id,
            author=p.author,
            model_id=p.model_id,
            system_prompt_hash=p.system_prompt_hash,
            signed_at=p.signed_at,
            signature=p.signature,
            is_official_verified=p.is_official_verified,
        )
        is_valid = self._auditor.verify_agent_profile(pkg, req.actual_system_prompt)
        reason = (
            "Profile signature and prompt integrity verified successfully."
            if is_valid
            else "Profile verification failed: signature mismatch or altered system prompt."
        )
        return VerifyProfileResponse(is_valid=is_valid, reason=reason)


_service_instance: SandboxZeroLeakagePiiService | None = None


def get_sandbox_zero_leakage_pii_service() -> SandboxZeroLeakagePiiService:
    """Singleton getter for SandboxZeroLeakagePiiService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SandboxZeroLeakagePiiService()
    return _service_instance
