"""
[POS] app/services/security/air_gapped_sovereignty_service.py
[INPUT] myrm_agent_harness.core.security.air_gapped_sovereignty, app.schemas.air_gapped_sovereignty
[OUTPUT] AirGappedSovereigntyService, get_air_gapped_sovereignty_service

Thread-safe service managing air-gapped offline trust store, sovereign model fallback,
evidentiary archive bundling, and commercial GM cryptography.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.air_gapped_sovereignty import (
    AirGappedSovereigntyFacade,
    AuditBundleRecord,
    ModelFallbackTarget,
)
from myrm_agent_harness.core.security.air_gapped_sovereignty import (
    NetworkConnectivityModeEnum as HarnessModeEnum,
)

from app.schemas.air_gapped_sovereignty import (
    AirGappedSovereigntyMetricsResponse,
    AuditBundlePackRequest,
    AuditBundleResponse,
    AuditBundleVerifyRequest,
    AuditBundleVerifyResponse,
    ImportCrlRequest,
    ImportCrlResponse,
    ModelFallbackTargetSchema,
    ModelResolutionRequest,
    ModelResolutionResponse,
    ModeResponse,
    ModeUpdateRequest,
    NetworkConnectivityModeEnum,
    OfflineCertValidationRequest,
    OfflineCertValidationResponse,
    SovereignCryptoHashRequest,
    SovereignCryptoHashResponse,
)


class AirGappedSovereigntyService:
    """Service wrapping air-gapped sovereign operations and offline trust validation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._facade = AirGappedSovereigntyFacade(
            mode=HarnessModeEnum.AIR_GAPPED_ISOLATED,
            default_sovereign_target=ModelFallbackTarget(
                model_id="qwen2.5-coder:32b",
                endpoint_url="http://127.0.0.1:11434/v1",
                provider="ollama",
                is_local_sovereign=True,
                context_window=32768,
            ),
        )
        self._total_revoked_count = 0

    def set_network_mode(self, req: ModeUpdateRequest) -> ModeResponse:
        """Update active network isolation mode."""
        harness_mode = HarnessModeEnum(req.mode.value)
        with self._lock:
            self._facade.set_network_mode(harness_mode)
        return ModeResponse(active_mode=req.mode)

    def get_network_mode(self) -> ModeResponse:
        """Get current network isolation mode."""
        with self._lock:
            mode = self._facade.get_network_mode()
        return ModeResponse(active_mode=NetworkConnectivityModeEnum(mode.value))

    def validate_offline_certificate(
        self, req: OfflineCertValidationRequest
    ) -> OfflineCertValidationResponse:
        """Validate certificate against offline trust store and CRL."""
        with self._lock:
            res = self._facade.validate_offline_certificate(
                cert_pem=req.cert_pem,
                cert_serial=req.cert_serial,
                issuer_ca=req.issuer_ca,
                valid_until=req.valid_until,
            )
        return OfflineCertValidationResponse(
            is_valid=res.is_valid,
            reason=res.reason,
            ca_name=res.ca_name,
            is_revoked=res.is_revoked,
            fingerprint_sm3=res.fingerprint_sm3,
        )

    def import_crl(self, req: ImportCrlRequest) -> ImportCrlResponse:
        """Import revoked certificate serials list."""
        with self._lock:
            added = self._facade.import_crl(req.revoked_serials)
            self._total_revoked_count += added
            total = self._total_revoked_count
        return ImportCrlResponse(imported_count=added, total_revoked_count=total)

    def resolve_model(self, req: ModelResolutionRequest) -> ModelResolutionResponse:
        """Resolve model execution endpoint under network constraints."""
        with self._lock:
            target, was_fallback, reason = self._facade.resolve_model(
                requested_model_id=req.requested_model_id,
                is_remote_healthy=req.is_remote_healthy,
            )
            current_mode = self._facade.get_network_mode()

        schema_target = ModelFallbackTargetSchema(
            model_id=target.model_id,
            endpoint_url=target.endpoint_url,
            provider=target.provider,
            is_local_sovereign=target.is_local_sovereign,
            context_window=target.context_window,
        )
        return ModelResolutionResponse(
            effective_target=schema_target,
            was_fallback=was_fallback,
            reason=reason,
            active_mode=NetworkConnectivityModeEnum(current_mode.value),
        )

    def pack_audit_bundle(self, req: AuditBundlePackRequest) -> AuditBundleResponse:
        """Seal records into tamper-evident SM3 audit bundle."""
        with self._lock:
            bundle = self._facade.seal_audit_bundle(
                records=req.records,
                bundle_id=req.bundle_id,
                metadata=req.metadata,
            )
        return AuditBundleResponse(
            bundle_id=bundle.bundle_id,
            timestamp=bundle.timestamp,
            record_count=bundle.record_count,
            sm3_root_digest=bundle.sm3_root_digest,
            is_sealed=bundle.is_sealed,
            metadata=bundle.metadata,
        )

    def verify_audit_bundle(self, req: AuditBundleVerifyRequest) -> AuditBundleVerifyResponse:
        """Verify evidentiary bundle integrity."""
        harness_bundle = AuditBundleRecord(
            bundle_id=req.bundle.bundle_id,
            timestamp=req.bundle.timestamp,
            record_count=req.bundle.record_count,
            sm3_root_digest=req.bundle.sm3_root_digest,
            is_sealed=req.bundle.is_sealed,
            metadata=req.bundle.metadata,
        )
        with self._lock:
            is_valid = self._facade.verify_audit_bundle(
                bundle=harness_bundle,
                raw_records=req.raw_records,
            )
        reason = (
            "Evidentiary audit bundle verified successfully with matching SM3 root digest."
            if is_valid
            else "Evidentiary audit bundle validation failed: digest or record mismatch."
        )
        return AuditBundleVerifyResponse(is_valid=is_valid, reason=reason)

    def compute_sm3_hash(self, req: SovereignCryptoHashRequest) -> SovereignCryptoHashResponse:
        """Compute SM3 cryptographic digest."""
        with self._lock:
            digest = self._facade.hash_sovereign_data(req.data)
        return SovereignCryptoHashResponse(
            algorithm="SM3 (GM/T 0004-2012)",
            sm3_digest=digest,
        )

    def get_metrics(self) -> AirGappedSovereigntyMetricsResponse:
        """Get air-gapped sovereignty operational metrics."""
        with self._lock:
            m = self._facade.get_metrics()
        return AirGappedSovereigntyMetricsResponse(
            total_offline_validations=m.total_offline_validations,
            valid_certificates_count=m.valid_certificates_count,
            crl_revocation_hits=m.crl_revocation_hits,
            model_fallback_events=m.model_fallback_events,
            audit_bundles_sealed=m.audit_bundles_sealed,
        )


_SERVICE_INSTANCE: Optional[AirGappedSovereigntyService] = None
_SERVICE_LOCK = threading.Lock()


def get_air_gapped_sovereignty_service() -> AirGappedSovereigntyService:
    """Get singleton instance of AirGappedSovereigntyService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = AirGappedSovereigntyService()
        return _SERVICE_INSTANCE
