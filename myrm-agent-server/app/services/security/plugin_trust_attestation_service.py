"""Service implementation for Plugin Trust Chain and Dynamic Capability Attestation.

[POS] app/services/security/plugin_trust_attestation_service.py
[INPUT] myrm_agent_harness.core.security.plugin_trust_attestation, app.schemas.plugin_trust_attestation
[OUTPUT] PluginTrustAttestationService, get_plugin_trust_attestation_service
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.plugin_trust_attestation.trust_verifier import (
    PluginTrustChainVerifier,
)
from myrm_agent_harness.core.security.plugin_trust_attestation.types import (
    CapabilityAttestationToken,
    PluginCapabilityManifest,
    PluginSignaturePackage,
    PluginTrustTier,
)

from app.schemas.plugin_trust_attestation import (
    AttestationTokenResponse,
    IssueAttestationTokenRequest,
    SignedPluginPackageResponse,
    SignPluginPackageRequest,
    ValidateOperationRequest,
    ValidateOperationResponse,
    VerifyPluginPackageRequest,
    VerifyPluginPackageResponse,
)

logger = logging.getLogger(__name__)


class PluginTrustAttestationService:
    """Business service governing vetted plugin trust chain and capability attestations."""

    def __init__(self, verifier: PluginTrustChainVerifier | None = None) -> None:
        self._verifier = verifier or PluginTrustChainVerifier()

    def compute_files_digest(self, files: dict[str, str]) -> str:
        """Compute deterministic canonical digest across payload files."""
        return self._verifier.compute_payload_digest(files)

    def sign_package(self, req: SignPluginPackageRequest) -> SignedPluginPackageResponse:
        """Sign release payload using vetted pipeline key."""
        try:
            trust_tier = PluginTrustTier(req.trust_tier)
        except ValueError:
            trust_tier = PluginTrustTier.UNREVIEWED_COMMUNITY

        pkg = self._verifier.sign_plugin_package(
            plugin_id=req.plugin_id,
            version=req.version,
            payload_sha256=req.payload_sha256,
            trust_tier=trust_tier,
            signer_identity=req.signer_identity,
        )

        return SignedPluginPackageResponse(
            plugin_id=pkg.plugin_id,
            version=pkg.version,
            payload_sha256=pkg.payload_sha256,
            signature=pkg.signature,
            signer_identity=pkg.signer_identity,
            trust_tier=pkg.trust_tier.value,
            signed_at=pkg.signed_at,
        )

    def verify_package(self, req: VerifyPluginPackageRequest) -> VerifyPluginPackageResponse:
        """Verify authenticity, integrity, and trust tier of a plugin package."""
        try:
            tier = PluginTrustTier(req.package.trust_tier)
        except ValueError:
            tier = PluginTrustTier.UNREVIEWED_COMMUNITY

        pkg = PluginSignaturePackage(
            plugin_id=req.package.plugin_id,
            version=req.package.version,
            payload_sha256=req.package.payload_sha256,
            signature=req.package.signature,
            signer_identity=req.package.signer_identity,
            trust_tier=tier,
            signed_at=req.package.signed_at,
        )

        outcome = self._verifier.verify_package(
            package=pkg,
            actual_payload_sha256=req.actual_payload_sha256,
        )

        return VerifyPluginPackageResponse(
            is_valid=outcome.is_valid,
            trust_tier=outcome.trust_tier.value,
            error_message=outcome.error_message,
        )

    def issue_token(self, req: IssueAttestationTokenRequest) -> AttestationTokenResponse:
        """Issue dynamic time-bound capability proof token."""
        manifest = PluginCapabilityManifest(
            plugin_id=req.plugin_id,
            version=req.version,
            network_domains=req.network_domains,
            file_access_scope=req.file_access_scope,
            allow_shell_exec=req.allow_shell_exec,
        )

        token = self._verifier.issue_attestation_token(
            manifest=manifest,
            validity_seconds=req.validity_seconds,
        )

        return AttestationTokenResponse(
            token_id=token.token_id,
            plugin_id=token.plugin_id,
            granted_domains=token.granted_domains,
            granted_file_scope=token.granted_file_scope,
            allow_shell=token.allow_shell,
            issued_at=token.issued_at,
            expires_at=token.expires_at,
            token_hmac=token.token_hmac,
        )

    def validate_operation(self, req: ValidateOperationRequest) -> ValidateOperationResponse:
        """Validate whether a runtime sandbox action matches the attestation token."""
        token = CapabilityAttestationToken(
            token_id=req.token.token_id,
            plugin_id=req.token.plugin_id,
            granted_domains=req.token.granted_domains,
            granted_file_scope=req.token.granted_file_scope,
            allow_shell=req.token.allow_shell,
            issued_at=req.token.issued_at,
            expires_at=req.token.expires_at,
            token_hmac=req.token.token_hmac,
        )

        allowed = self._verifier.verify_operation_permission(
            token=token,
            target_domain=req.target_domain,
            requires_shell=req.requires_shell,
        )

        if allowed:
            reason = "Operation is authorized by active capability attestation token."
        else:
            reason = "Operation is rejected due to attestation scope violation, expiry, or invalid signature."

        return ValidateOperationResponse(
            allowed=allowed,
            reason=reason,
        )


_service_instance: PluginTrustAttestationService | None = None


def get_plugin_trust_attestation_service() -> PluginTrustAttestationService:
    """Singleton getter for PluginTrustAttestationService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PluginTrustAttestationService()
    return _service_instance
