"""
[POS] tests/unit/test_keychain_rest_encryption_service.py
[INPUT] pytest, tmp_path, pathlib, myrm_agent_harness, app.schemas.keychain_rest_encryption, app.services.security.keychain_rest_encryption_service
[OUTPUT] Unit tests for KeychainRestEncryptionService

Validates service-level keychain status queries, text/file transparent encryption roundtrips,
metrics inspection, and instant emergency purge.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.core.security.keychain_rest_encryption import (
    KeychainBackendType,
    KeychainRestEncryptionSuite,
)

from app.schemas.keychain_rest_encryption import (
    DecryptFileRequest,
    DecryptTextRequest,
    EncryptFileRequest,
    EncryptionDomainEnum,
    EncryptTextRequest,
    KeyPurgeScopeEnum,
    PurgeCredentialsRequest,
)
from app.services.security.keychain_rest_encryption_service import (
    KeychainRestEncryptionService,
)


def _create_test_service() -> KeychainRestEncryptionService:
    suite = KeychainRestEncryptionSuite(
        service_name="test.myrm.server.service",
        account_name="test_service_acc",
        force_backend=KeychainBackendType.FALLBACK_EPHEMERAL,
    )
    return KeychainRestEncryptionService(suite=suite)


def test_service_status_and_self_test() -> None:
    """Validate status retrieval and cryptographic self-test via service."""
    service = _create_test_service()

    status = service.get_status()
    assert status.backend_type.value == "FALLBACK_EPHEMERAL"
    assert not status.is_hardware_backed
    assert len(status.active_domains) >= 4

    self_test_res = service.self_test()
    assert self_test_res.passed is True
    assert self_test_res.envelope_id.startswith("env-")


def test_service_text_encryption_roundtrip() -> None:
    """Validate string text transparent encryption and decryption through service."""
    service = _create_test_service()
    raw_text = "HighlySensitiveFinancialPayroll:Executive-Comp-2026"

    enc_req = EncryptTextRequest(
        text=raw_text,
        domain=EncryptionDomainEnum.FINANCIAL_DOCS,
    )
    enc_res = service.encrypt_text(enc_req)
    assert enc_res.envelope.domain == EncryptionDomainEnum.FINANCIAL_DOCS
    assert enc_res.envelope.ciphertext_hex != ""

    dec_req = DecryptTextRequest(envelope=enc_res.envelope)
    dec_res = service.decrypt_text(dec_req)
    assert dec_res.plaintext == raw_text

    metrics = service.get_metrics()
    assert metrics.encryptions_total >= 1
    assert metrics.decryptions_total >= 1


def test_service_file_encryption_roundtrip(tmp_path: Path) -> None:
    """Validate file encryption and decryption on disk."""
    service = _create_test_service()

    src = tmp_path / "ehr_record.txt"
    enc = tmp_path / "ehr_record.enc"
    dec = tmp_path / "ehr_record_dec.txt"

    content = "Patient Health Dossier: Allergies=Penicillin"
    src.write_text(content, encoding="utf-8")

    enc_req = EncryptFileRequest(
        source_path=str(src),
        dest_path=str(enc),
        domain=EncryptionDomainEnum.HEALTH_RECORDS,
    )
    enc_res = service.encrypt_file(enc_req)
    assert Path(enc_res.dest_path).exists()

    dec_req = DecryptFileRequest(
        source_path=str(enc),
        dest_path=str(dec),
    )
    dec_res = service.decrypt_file(dec_req)
    assert dec_res.size_bytes == len(content.encode("utf-8"))
    assert Path(dec_res.dest_path).read_text(encoding="utf-8") == content


def test_service_purge_credentials() -> None:
    """Validate instant purge via service."""
    service = _create_test_service()

    # Pre-populate key into memory by encrypting
    service.encrypt_text(EncryptTextRequest(text="dummy", domain=EncryptionDomainEnum.GENERAL_REST))
    assert service.get_status().cached_in_memory is True

    purge_req = PurgeCredentialsRequest(scope=KeyPurgeScopeEnum.KEYCHAIN_AND_MEMORY)
    purge_res = service.purge_credentials(purge_req)

    assert purge_res.keys_zeroized >= 1
    assert purge_res.keychain_deleted is True
    assert service.get_status().cached_in_memory is False
