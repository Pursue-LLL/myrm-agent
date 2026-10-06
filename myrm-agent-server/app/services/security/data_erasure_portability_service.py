"""Service implementation for Verifiable Cryptographic Erasure and Data Portability.

[POS] app/services/security/data_erasure_portability_service.py
[INPUT] myrm_agent_harness.core.security.data_erasure_portability, app.schemas.data_erasure_portability
[OUTPUT] DataErasurePortabilityService, get_data_erasure_portability_service
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.core.security.data_erasure_portability.crypto_erasure import (
    CryptographicErasureEngine,
)
from myrm_agent_harness.core.security.data_erasure_portability.portability import (
    DataPortabilityExporter,
)
from myrm_agent_harness.core.security.data_erasure_portability.shredder import (
    SecureStorageShredder,
)
from myrm_agent_harness.core.security.data_erasure_portability.types import (
    DataPortabilityBundle,
    DeletionCertificate,
    ErasureMethod,
    ShreddingPassConfig,
)

from app.schemas.data_erasure_portability import (
    DeletionCertificateResponse,
    ErasureResultResponse,
    ExecuteErasureRequest,
    ExportPortabilityBundleRequest,
    PortabilityBundleResponse,
    RegisterTenantKeyRequest,
    ShredPathRequest,
    ShredPathResponse,
    TenantKeyResponse,
    VerifyBundleRequest,
    VerifyBundleResponse,
    VerifyCertificateRequest,
    VerifyCertificateResponse,
)

logger = logging.getLogger(__name__)


class DataErasurePortabilityService:
    """Business service governing GDPR Article 17 erasure and Article 20 data portability."""

    def __init__(
        self,
        crypto_engine: CryptographicErasureEngine | None = None,
        shredder: SecureStorageShredder | None = None,
        exporter: DataPortabilityExporter | None = None,
    ) -> None:
        self._crypto_engine = crypto_engine or CryptographicErasureEngine()
        self._shredder = shredder or SecureStorageShredder()
        self._exporter = exporter or DataPortabilityExporter()

    def register_tenant_key(self, req: RegisterTenantKeyRequest) -> TenantKeyResponse:
        """Register or re-key an active encryption key for a tenant."""
        fp = self._crypto_engine.register_tenant_key(req.tenant_id)
        return TenantKeyResponse(
            tenant_id=req.tenant_id,
            key_fingerprint=fp,
            status="ACTIVE",
        )

    def execute_erasure(self, req: ExecuteErasureRequest) -> ErasureResultResponse:
        """Execute irreversible cryptographic erasure and optional storage volume shredding."""
        total_shredded_bytes = 0
        total_shredded_files = 0

        # 1. Physical multi-pass shredding if path is provided
        if req.physical_path_to_shred:
            path = Path(req.physical_path_to_shred).resolve()
            if path.is_file():
                b = self._shredder.shred_file(path)
                total_shredded_bytes += b
                total_shredded_files += 1
            elif path.is_dir():
                f_count, b = self._shredder.shred_directory(path)
                total_shredded_bytes += b
                total_shredded_files += f_count

        # 2. Cryptographic DEK destruction
        result = self._crypto_engine.execute_cryptographic_erasure(
            tenant_id=req.tenant_id,
            target_resource_types=req.target_resource_types,
            shredded_bytes=total_shredded_bytes,
            signer_identity=req.signer_identity,
        )

        cert_resp: DeletionCertificateResponse | None = None
        if result.certificate is not None:
            c = result.certificate
            cert_resp = DeletionCertificateResponse(
                certificate_id=c.certificate_id,
                tenant_id=c.tenant_id,
                erasure_method=c.erasure_method.value,
                target_resource_types=c.target_resource_types,
                shredded_bytes=c.shredded_bytes,
                payload_checksum_prior=c.payload_checksum_prior,
                timestamp=c.timestamp,
                signer_identity=c.signer_identity,
                certificate_signature=c.certificate_signature,
            )

        return ErasureResultResponse(
            success=result.success,
            tenant_id=result.tenant_id,
            erasure_method=result.erasure_method.value,
            certificate=cert_resp,
            shredded_files_count=total_shredded_files,
            shredded_bytes_count=total_shredded_bytes,
            error_message=result.error_message,
        )

    def verify_certificate(self, req: VerifyCertificateRequest) -> VerifyCertificateResponse:
        """Verify authenticity and tamper-resistance of a DeletionCertificate."""
        c = req.certificate
        try:
            method = ErasureMethod(c.erasure_method)
        except ValueError:
            return VerifyCertificateResponse(
                is_valid=False,
                reason="Invalid erasure method specified in certificate.",
            )

        cert = DeletionCertificate(
            certificate_id=c.certificate_id,
            tenant_id=c.tenant_id,
            erasure_method=method,
            target_resource_types=c.target_resource_types,
            shredded_bytes=c.shredded_bytes,
            payload_checksum_prior=c.payload_checksum_prior,
            timestamp=c.timestamp,
            signer_identity=c.signer_identity,
            certificate_signature=c.certificate_signature,
        )

        is_valid = self._crypto_engine.verify_deletion_certificate(cert)
        if is_valid:
            reason = "Deletion certificate signature is verified and authentic."
        else:
            reason = "Deletion certificate signature verification failed or payload tampered."

        return VerifyCertificateResponse(is_valid=is_valid, reason=reason)

    def export_bundle(self, req: ExportPortabilityBundleRequest) -> PortabilityBundleResponse:
        """Package user data into a signed GDPR Article 20 portable container."""
        bundle = self._exporter.export_bundle(
            tenant_id=req.tenant_id,
            conversations=req.conversations,
            memory_entries=req.memory_entries,
            agent_configs=req.agent_configs,
        )

        return PortabilityBundleResponse(
            bundle_id=bundle.bundle_id,
            tenant_id=bundle.tenant_id,
            exported_at=bundle.exported_at,
            conversations=bundle.conversations,
            memory_entries=bundle.memory_entries,
            agent_configs=bundle.agent_configs,
            bundle_sha256=bundle.bundle_sha256,
            bundle_signature=bundle.bundle_signature,
        )

    def verify_bundle(self, req: VerifyBundleRequest) -> VerifyBundleResponse:
        """Verify integrity and signature of a portability bundle."""
        b = req.bundle
        bundle = DataPortabilityBundle(
            bundle_id=b.bundle_id,
            tenant_id=b.tenant_id,
            exported_at=b.exported_at,
            conversations=b.conversations,
            memory_entries=b.memory_entries,
            agent_configs=b.agent_configs,
            bundle_sha256=b.bundle_sha256,
            bundle_signature=b.bundle_signature,
        )

        is_valid = self._exporter.verify_bundle_integrity(bundle)
        if is_valid:
            reason = "Portability bundle digest and signature verified successfully."
        else:
            reason = "Portability bundle corrupted, tampered, or invalid signature."

        return VerifyBundleResponse(is_valid=is_valid, reason=reason)

    def shred_path(self, req: ShredPathRequest) -> ShredPathResponse:
        """Directly shred a specified file or directory."""
        path = Path(req.path).resolve()
        cfg = ShreddingPassConfig(passes=req.passes)

        if path.is_file():
            b = self._shredder.shred_file(path, config=cfg)
            return ShredPathResponse(
                target_path=str(path),
                files_shredded=1,
                bytes_shredded=b,
                success=True,
            )
        if path.is_dir():
            f_count, b = self._shredder.shred_directory(path, config=cfg)
            return ShredPathResponse(
                target_path=str(path),
                files_shredded=f_count,
                bytes_shredded=b,
                success=True,
            )

        return ShredPathResponse(
            target_path=str(path),
            files_shredded=0,
            bytes_shredded=0,
            success=False,
        )


_service_instance: DataErasurePortabilityService | None = None


def get_data_erasure_portability_service() -> DataErasurePortabilityService:
    """Singleton getter for DataErasurePortabilityService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = DataErasurePortabilityService()
    return _service_instance
