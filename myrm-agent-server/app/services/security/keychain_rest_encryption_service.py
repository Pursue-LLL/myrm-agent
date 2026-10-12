"""
[POS] app/services/security/keychain_rest_encryption_service.py
[INPUT] pathlib, myrm_agent_harness.core.security.keychain_rest_encryption, app.schemas.keychain_rest_encryption
[OUTPUT] KeychainRestEncryptionService, get_keychain_rest_encryption_service

Domain service encapsulating OS keychain integration, transparent rest encryption,
cold-boot guards, and instant emergency purge.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.core.security.keychain_rest_encryption import (
    CipherEnvelope,
    EncryptionDomain,
    KeychainRestEncryptionSuite,
    KeychainStatus,
    KeyPurgeScope,
    PurgeReport,
)

from app.schemas.keychain_rest_encryption import (
    CipherEnvelopeResponse,
    DecryptFileRequest,
    DecryptFileResponse,
    DecryptTextRequest,
    DecryptTextResponse,
    EncryptFileRequest,
    EncryptFileResponse,
    EncryptionDomainEnum,
    EncryptTextRequest,
    EncryptTextResponse,
    KeychainBackendTypeEnum,
    KeychainSelfTestResponse,
    KeychainStatusResponse,
    KeyPurgeScopeEnum,
    PurgeCredentialsRequest,
    PurgeCredentialsResponse,
    TransparentRestMetricsResponse,
)


class KeychainRestEncryptionService:
    """Service mediating application requests with the underlying harness keychain suite."""

    def __init__(self, suite: KeychainRestEncryptionSuite | None = None) -> None:
        self._suite = suite or KeychainRestEncryptionSuite(
            service_name="com.myrm.agent.server",
            account_name="server_master_root_key",
        )

    def get_status(self) -> KeychainStatusResponse:
        """Fetch current status of OS keychain and encryption-at-rest."""
        status: KeychainStatus = self._suite.get_status()
        return KeychainStatusResponse(
            backend_type=KeychainBackendTypeEnum(status.backend_type.value),
            is_hardware_backed=status.is_hardware_backed,
            has_master_key=status.has_master_key,
            master_key_fingerprint=status.master_key_fingerprint,
            cached_in_memory=status.cached_in_memory,
            degradation_warning=status.degradation_warning,
            active_domains=list(status.active_domains),
        )

    def encrypt_text(self, req: EncryptTextRequest) -> EncryptTextResponse:
        """Encrypt string text transparently."""
        domain = EncryptionDomain(req.domain.value)
        envelope = self._suite.encrypt_text(req.text, domain=domain)
        return EncryptTextResponse(envelope=self._to_envelope_response(envelope))

    def decrypt_text(self, req: DecryptTextRequest) -> DecryptTextResponse:
        """Decrypt sealed envelope back to plaintext string."""
        envelope = self._from_envelope_response(req.envelope)
        plaintext = self._suite.decrypt_text(envelope)
        return DecryptTextResponse(plaintext=plaintext)

    def encrypt_file(self, req: EncryptFileRequest) -> EncryptFileResponse:
        """Encrypt file on disk and return envelope descriptor."""
        domain = EncryptionDomain(req.domain.value)
        source = Path(req.source_path)
        dest = Path(req.dest_path)
        envelope = self._suite.encrypt_file(source, dest, domain=domain)
        return EncryptFileResponse(
            envelope=self._to_envelope_response(envelope),
            dest_path=str(dest),
        )

    def decrypt_file(self, req: DecryptFileRequest) -> DecryptFileResponse:
        """Decrypt file on disk and restore plaintext."""
        source = Path(req.source_path)
        dest = Path(req.dest_path)
        plaintext_bytes = self._suite.decrypt_file(source, dest)
        return DecryptFileResponse(
            dest_path=str(dest),
            size_bytes=len(plaintext_bytes),
        )

    def purge_credentials(self, req: PurgeCredentialsRequest) -> PurgeCredentialsResponse:
        """Execute instant emergency purge across memory and keychain."""
        scope = KeyPurgeScope(req.scope.value)
        report: PurgeReport = self._suite.purge_credentials(scope=scope)
        return PurgeCredentialsResponse(
            purge_id=report.purge_id,
            scope=KeyPurgeScopeEnum(report.scope.value),
            backend_type=KeychainBackendTypeEnum(report.backend_type.value),
            keys_zeroized=report.keys_zeroized,
            keychain_deleted=report.keychain_deleted,
            timestamp=report.timestamp,
        )

    def self_test(self) -> KeychainSelfTestResponse:
        """Execute end-to-end cryptographic self-test."""
        res = self._suite.self_test()
        return KeychainSelfTestResponse(
            passed=bool(res["passed"]),
            backend=str(res["backend"]),
            hardware_backed=bool(res["hardware_backed"]),
            envelope_id=str(res["envelope_id"]),
            fingerprint=str(res["fingerprint"]),
        )

    def get_metrics(self) -> TransparentRestMetricsResponse:
        """Fetch cumulative cryptographic metrics."""
        m = self._suite.metrics
        return TransparentRestMetricsResponse(
            encryptions_total=m.encryptions_total,
            decryptions_total=m.decryptions_total,
            decryption_failures=m.decryption_failures,
            purges_total=m.purges_total,
            domain_key_derivations=m.domain_key_derivations,
            files_encrypted_total=m.files_encrypted_total,
            files_decrypted_total=m.files_decrypted_total,
        )

    @staticmethod
    def _to_envelope_response(env: CipherEnvelope) -> CipherEnvelopeResponse:
        return CipherEnvelopeResponse(
            envelope_id=env.envelope_id,
            domain=EncryptionDomainEnum(env.domain.value),
            salt_hex=env.salt_hex,
            nonce_hex=env.nonce_hex,
            tag_hex=env.tag_hex,
            ciphertext_hex=env.ciphertext_hex,
            key_fingerprint=env.key_fingerprint,
            created_at=env.created_at,
        )

    @staticmethod
    def _from_envelope_response(resp: CipherEnvelopeResponse) -> CipherEnvelope:
        return CipherEnvelope(
            envelope_id=resp.envelope_id,
            domain=EncryptionDomain(resp.domain.value),
            salt_hex=resp.salt_hex,
            nonce_hex=resp.nonce_hex,
            tag_hex=resp.tag_hex,
            ciphertext_hex=resp.ciphertext_hex,
            key_fingerprint=resp.key_fingerprint,
            created_at=resp.created_at,
        )


_default_service: KeychainRestEncryptionService | None = None


def get_keychain_rest_encryption_service() -> KeychainRestEncryptionService:
    """Dependency injection provider for KeychainRestEncryptionService."""
    global _default_service
    if _default_service is None:
        _default_service = KeychainRestEncryptionService()
    return _default_service
