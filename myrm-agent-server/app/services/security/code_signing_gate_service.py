"""
[POS] app/services/security/code_signing_gate_service.py
[INPUT] myrm_agent_harness.core.security.code_signing_gate, app.schemas.code_signing_gate
[OUTPUT] CodeSigningGateService, get_code_signing_gate_service

Thread-safe service managing developer identity attestation, Ed25519 agent package code signing,
manifest integrity hashing, and enterprise supply chain trust policy gates.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.code_signing_gate import (
    CodeSigningGateSuite,
)
from myrm_agent_harness.core.security.code_signing_gate import (
    DeveloperCertificateInfo as HarnessCertInfo,
)
from myrm_agent_harness.core.security.code_signing_gate import (
    PackageManifestEntry as HarnessManifestEntry,
)
from myrm_agent_harness.core.security.code_signing_gate import (
    SignedPackageDescriptor as HarnessPackageDescriptor,
)
from myrm_agent_harness.core.security.code_signing_gate import (
    SupplyChainTrustPolicyEnum as HarnessTrustPolicy,
)

from app.schemas.code_signing_gate import (
    CodeSigningGateMetricsResponse,
    PackageManifestEntrySchema,
    PackageSignRequest,
    PackageVerificationVerdictEnum,
    PackageVerifyRequest,
    PackageVerifyResponse,
    SignedPackageResponse,
    SupplyChainTrustPolicyEnum,
    TrustPolicyResponse,
    TrustPolicyUpdateRequest,
)


class CodeSigningGateService:
    """Service enforcing developer code signatures and enterprise supply chain policies."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suite = CodeSigningGateSuite()

    def sign_package(self, req: PackageSignRequest) -> SignedPackageResponse:
        """Sign agent/skill package using developer private key and construct signed descriptor."""
        cert_info: HarnessCertInfo | None = None
        if req.cert_info is not None:
            cert_info = HarnessCertInfo(
                developer_id=req.cert_info.developer_id,
                developer_name=req.cert_info.developer_name,
                org_dn=req.cert_info.org_dn,
                issuer_ca=req.cert_info.issuer_ca,
                cert_serial=req.cert_info.cert_serial,
                valid_until=req.cert_info.valid_until,
                public_key_pem=req.cert_info.public_key_pem,
                is_internal_enterprise=req.cert_info.is_internal_enterprise,
            )

        # Convert files to format expected by harness
        files_dict: dict[str, str | bytes] = {k: v for k, v in req.files.items()}

        with self._lock:
            pkg = self._suite.sign_package(
                package_id=req.package_id,
                package_name=req.package_name,
                version=req.version,
                files=files_dict,
                private_key_pem=req.private_key_pem,
                cert_info=cert_info,
            )

        manifest_schemas = [
            PackageManifestEntrySchema(
                file_path=e.file_path,
                sha256_hash=e.sha256_hash,
                size_bytes=e.size_bytes,
            )
            for e in pkg.manifest_entries
        ]

        return SignedPackageResponse(
            package_id=pkg.package_id,
            package_name=pkg.package_name,
            version=pkg.version,
            manifest_entries=manifest_schemas,
            canonical_manifest_digest=pkg.canonical_manifest_digest,
            signature_b64=pkg.signature_b64,
            cert_info=req.cert_info,
        )

    def verify_package(self, req: PackageVerifyRequest) -> PackageVerifyResponse:
        """Verify package code signature, asset digest integrity, and enterprise trust policy."""
        cert_info: HarnessCertInfo | None = None
        if req.package.cert_info is not None:
            c = req.package.cert_info
            cert_info = HarnessCertInfo(
                developer_id=c.developer_id,
                developer_name=c.developer_name,
                org_dn=c.org_dn,
                issuer_ca=c.issuer_ca,
                cert_serial=c.cert_serial,
                valid_until=c.valid_until,
                public_key_pem=c.public_key_pem,
                is_internal_enterprise=c.is_internal_enterprise,
            )

        manifest_entries = [
            HarnessManifestEntry(
                file_path=e.file_path,
                sha256_hash=e.sha256_hash,
                size_bytes=e.size_bytes,
            )
            for e in req.package.manifest_entries
        ]

        harness_pkg = HarnessPackageDescriptor(
            package_id=req.package.package_id,
            package_name=req.package.package_name,
            version=req.package.version,
            manifest_entries=manifest_entries,
            canonical_manifest_digest=req.package.canonical_manifest_digest,
            signature_b64=req.package.signature_b64,
            cert_info=cert_info,
        )

        actual_files_dict: dict[str, str | bytes] | None = None
        if req.actual_files is not None:
            actual_files_dict = {k: v for k, v in req.actual_files.items()}

        with self._lock:
            res = self._suite.verify_package(
                package=harness_pkg,
                actual_files=actual_files_dict,
            )

        verdict_val = PackageVerificationVerdictEnum(res.verdict.value)
        return PackageVerifyResponse(
            is_allowed=res.is_allowed,
            verdict=verdict_val,
            reason=res.reason,
            verified_developer=res.verified_developer,
            cert_serial=res.cert_serial,
            is_enterprise_verified=res.is_enterprise_verified,
        )

    def get_policy(self) -> TrustPolicyResponse:
        """Retrieve current active enterprise supply chain policy."""
        with self._lock:
            pol = self._suite.get_policy()
        return TrustPolicyResponse(active_policy=SupplyChainTrustPolicyEnum(pol.value))

    def set_policy(self, req: TrustPolicyUpdateRequest) -> TrustPolicyResponse:
        """Update enterprise supply chain trust policy."""
        harness_pol = HarnessTrustPolicy(req.policy.value)
        with self._lock:
            self._suite.set_policy(harness_pol)
        return TrustPolicyResponse(active_policy=req.policy)

    def revoke_certificate(self, cert_serial: str) -> bool:
        """Revoke a compromised developer certificate serial."""
        with self._lock:
            self._suite.revoke_certificate(cert_serial)
        return True

    def get_metrics(self) -> CodeSigningGateMetricsResponse:
        """Inspect cumulative code signing and supply chain metrics."""
        with self._lock:
            m = self._suite.get_metrics()

        return CodeSigningGateMetricsResponse(
            total_verifications=m.total_verifications,
            verified_count=m.verified_count,
            blocked_untrusted_count=m.blocked_untrusted_count,
            tampered_count=m.tampered_count,
            signature_failures=m.signature_failures,
        )


_SERVICE_INSTANCE: Optional[CodeSigningGateService] = None
_SERVICE_LOCK = threading.Lock()


def get_code_signing_gate_service() -> CodeSigningGateService:
    """Get singleton instance of CodeSigningGateService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = CodeSigningGateService()
        return _SERVICE_INSTANCE
