"""Pydantic schemas for Zero Knowledge Memory Vault and Provenance Watermarking (Item 159).

[INPUT]
- Passphrase payloads, memory seal requests, export requirements, watermark verification queries.

[OUTPUT]
- EncryptedEnvelopeDTO, ProvenanceWatermarkDTO, DistilledExportPackageDTO, ResidencyCheckResponse.

[POS]
- Server-side DTO contracts for Item 159 ZeroKnowledgeMemoryVaultAndAntiCloningProvenanceWatermarkingSuite.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MemorySensitivityTierDTO = Literal[
    "public_sharable",
    "team_internal",
    "strictly_private_pii",
]


class EncryptedEnvelopeDTO(BaseModel):
    """Envelope-encrypted memory payload protected by a local master key (KEK/DEK)."""

    ciphertext_hex: str
    iv_hex: str
    salt_hex: str
    encrypted_dek_hex: str
    algorithm: str = "AES-256-GCM-Simulated-HMAC"
    created_at: str = ""


class ProvenanceWatermarkDTO(BaseModel):
    """Provenance watermark identifying origin tenant, operator, and export timestamp."""

    tenant_id: str
    user_id: str
    timestamp_iso: str
    signature: str = ""


class DistilledMemoryItemDTO(BaseModel):
    """Distilled memory item classified by sensitivity tier with redaction metadata."""

    memory_id: str
    content: str
    sensitivity_tier: MemorySensitivityTierDTO
    category: str = "general"
    redacted: bool = False


class DistilledExportPackageDTO(BaseModel):
    """Export container carrying distilled memories alongside embedded invisible provenance watermarks."""

    tenant_id: str
    target_tier: MemorySensitivityTierDTO
    exported_at: str
    items: list[DistilledMemoryItemDTO] = Field(default_factory=list)
    watermarked_text: str = ""
    watermark_signature: str = ""


class SealMemoryRequest(BaseModel):
    """Payload to seal and store a memory using envelope encryption."""

    memory_id: str
    content: str
    sensitivity_tier: MemorySensitivityTierDTO = "team_internal"
    category: str = "general"
    passphrase: str


class UnsealMemoryRequest(BaseModel):
    """Payload to unseal a memory from its encrypted envelope."""

    memory_id: str
    passphrase: str


class ExportDistilledRequest(BaseModel):
    """Payload to export sanitized memories with embedded zero-width provenance watermark."""

    tenant_id: str
    user_id: str
    target_tier: MemorySensitivityTierDTO = "public_sharable"
    redact_pii: bool = True
    timestamp_iso: str | None = None


class VerifyWatermarkRequest(BaseModel):
    """Payload to scan and extract provenance watermark from potentially leaked text."""

    exported_text: str


class VerifyResidencyRequest(BaseModel):
    """Payload to verify current sandbox hardware and volume binding."""

    instance_guid: str
    volume_id: str
    tenant_id: str


class UnlockResidencyRequest(BaseModel):
    """Payload to unlock vault and rebind to new sandbox instance."""

    provided_passphrase: str
    expected_passphrase: str
    new_instance_guid: str
    new_volume_id: str
    tenant_id: str


class ResidencyCheckResponse(BaseModel):
    """Result of sandbox residency and anti-cloning environment verification."""

    allowed: bool
    diagnostic: str
