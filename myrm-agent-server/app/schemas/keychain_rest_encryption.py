"""
[POS] app/schemas/keychain_rest_encryption.py
[INPUT] pydantic, enum
[OUTPUT] KeychainBackendTypeEnum, EncryptionDomainEnum, KeyPurgeScopeEnum, KeychainStatusResponse, CipherEnvelopeResponse, EncryptTextRequest, EncryptTextResponse, DecryptTextRequest, DecryptTextResponse, EncryptFileRequest, EncryptFileResponse, DecryptFileRequest, DecryptFileResponse, PurgeCredentialsRequest, PurgeCredentialsResponse, KeychainSelfTestResponse, TransparentRestMetricsResponse

Pydantic schemas for Hardware-Rooted OS Keychain & Transparent Rest Encryption Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class KeychainBackendTypeEnum(StrEnum):
    """Underlying operating system keychain backend."""

    MACOS_KEYCHAIN = "MACOS_KEYCHAIN"
    WINDOWS_CREDENTIAL_MANAGER = "WINDOWS_CREDENTIAL_MANAGER"
    LINUX_SECRETSERVICE = "LINUX_SECRETSERVICE"
    FALLBACK_EPHEMERAL = "FALLBACK_EPHEMERAL"


class EncryptionDomainEnum(StrEnum):
    """Domain for cryptographic isolation and HKDF key derivation."""

    HEALTH_RECORDS = "HEALTH_RECORDS"
    FINANCIAL_DOCS = "FINANCIAL_DOCS"
    PERSONAL_JOURNAL = "PERSONAL_JOURNAL"
    AUTH_CREDENTIALS = "AUTH_CREDENTIALS"
    GENERAL_REST = "GENERAL_REST"


class KeyPurgeScopeEnum(StrEnum):
    """Scope of credentials to be wiped."""

    IN_MEMORY_ONLY = "IN_MEMORY_ONLY"
    KEYCHAIN_AND_MEMORY = "KEYCHAIN_AND_MEMORY"
    ALL_DOMAINS = "ALL_DOMAINS"


class CipherEnvelopeResponse(BaseModel):
    """Sealed AES-256-GCM cipher envelope."""

    envelope_id: str = Field(..., description="Unique envelope ID")
    domain: EncryptionDomainEnum = Field(..., description="Encryption domain")
    salt_hex: str = Field(..., description="Hex encoded HKDF salt")
    nonce_hex: str = Field(..., description="Hex encoded 96-bit AES-GCM nonce")
    tag_hex: str = Field(..., description="Hex encoded 128-bit authentication tag")
    ciphertext_hex: str = Field(..., description="Hex encoded ciphertext")
    key_fingerprint: str = Field(..., description="Truncated SHA-256 master key fingerprint")
    created_at: float = Field(..., description="Epoch created at")


class KeychainStatusResponse(BaseModel):
    """Status of OS keychain binding and rest encryption."""

    backend_type: KeychainBackendTypeEnum = Field(..., description="Active keychain backend")
    is_hardware_backed: bool = Field(..., description="True if backed by hardware enclave or TPM")
    has_master_key: bool = Field(..., description="True if master key exists")
    master_key_fingerprint: str | None = Field(default=None, description="Key fingerprint")
    cached_in_memory: bool = Field(..., description="True if master key currently in memory")
    degradation_warning: str | None = Field(default=None, description="Warning if degraded")
    active_domains: list[str] = Field(..., description="Active cryptographic domains")


class EncryptTextRequest(BaseModel):
    """Payload to encrypt plaintext string."""

    text: str = Field(..., min_length=1, description="Plaintext string")
    domain: EncryptionDomainEnum = Field(
        default=EncryptionDomainEnum.GENERAL_REST,
        description="Target security domain",
    )


class EncryptTextResponse(BaseModel):
    """Response containing sealed envelope."""

    envelope: CipherEnvelopeResponse = Field(..., description="Sealed envelope")


class DecryptTextRequest(BaseModel):
    """Payload to decrypt sealed envelope back to plaintext string."""

    envelope: CipherEnvelopeResponse = Field(..., description="Sealed envelope to decrypt")


class DecryptTextResponse(BaseModel):
    """Response containing decrypted plaintext string."""

    plaintext: str = Field(..., description="Decrypted plaintext string")


class EncryptFileRequest(BaseModel):
    """Payload to encrypt file on disk."""

    source_path: str = Field(..., min_length=1, description="Path to plaintext file")
    dest_path: str = Field(..., min_length=1, description="Destination path for encrypted envelope")
    domain: EncryptionDomainEnum = Field(
        default=EncryptionDomainEnum.GENERAL_REST,
        description="Target security domain",
    )


class EncryptFileResponse(BaseModel):
    """Response confirming file encryption."""

    envelope: CipherEnvelopeResponse = Field(..., description="Resulting envelope")
    dest_path: str = Field(..., description="Target envelope file path")


class DecryptFileRequest(BaseModel):
    """Payload to decrypt envelope file on disk."""

    source_path: str = Field(..., min_length=1, description="Path to encrypted envelope file")
    dest_path: str = Field(..., min_length=1, description="Destination path for plaintext file")


class DecryptFileResponse(BaseModel):
    """Response confirming file decryption."""

    dest_path: str = Field(..., description="Decrypted file path")
    size_bytes: int = Field(..., ge=0, description="Decrypted size in bytes")


class PurgeCredentialsRequest(BaseModel):
    """Payload to request instant cryptographic purge."""

    scope: KeyPurgeScopeEnum = Field(
        default=KeyPurgeScopeEnum.KEYCHAIN_AND_MEMORY,
        description="Scope of credentials to wipe",
    )


class PurgeCredentialsResponse(BaseModel):
    """Audit report for instant purge operation."""

    purge_id: str = Field(..., description="Purge operation identifier")
    scope: KeyPurgeScopeEnum = Field(..., description="Executed purge scope")
    backend_type: KeychainBackendTypeEnum = Field(..., description="Backend type")
    keys_zeroized: int = Field(..., ge=0, description="Count of memory keys zeroized")
    keychain_deleted: bool = Field(..., description="True if key removed from keychain")
    timestamp: float = Field(..., description="Timestamp of purge")


class KeychainSelfTestResponse(BaseModel):
    """Outcome of end-to-end cryptographic self-test."""

    passed: bool = Field(..., description="True if self test passed")
    backend: str = Field(..., description="Active keychain backend")
    hardware_backed: bool = Field(..., description="True if hardware backed")
    envelope_id: str = Field(..., description="Sample envelope ID")
    fingerprint: str = Field(..., description="Master key fingerprint")


class TransparentRestMetricsResponse(BaseModel):
    """Metrics tracking cryptographic operations."""

    encryptions_total: int = Field(..., ge=0)
    decryptions_total: int = Field(..., ge=0)
    decryption_failures: int = Field(..., ge=0)
    purges_total: int = Field(..., ge=0)
    domain_key_derivations: int = Field(..., ge=0)
    files_encrypted_total: int = Field(..., ge=0)
    files_decrypted_total: int = Field(..., ge=0)
