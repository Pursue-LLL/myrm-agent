"""
[POS] app/schemas/legal_audit_attestation.py
[INPUT] pydantic
[OUTPUT] DigestAlgorithmEnum, VerificationStatusEnum, AuditEntryCreateRequest, AuditEntryNodeResponse, TsaAnchorRequest, TsaTimestampTokenResponse, MerkleProofStepSchema, MerkleInclusionProofSchema, EvidenceDossierResponse, EvidenceDossierPackRequest, EvidenceDossierVerifyRequest, EvidenceDossierVerifyResponse, LedgerStatusResponse, LegalAuditMetricsResponse

Pydantic schemas for Legal-Grade Cryptographic Audit Evidence and Anti-Repudiation Attestation Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class DigestAlgorithmEnum(StrEnum):
    """Supported cryptographic hash digest algorithms."""

    SHA256 = "SHA-256"
    SHA384 = "SHA-384"
    SHA512 = "SHA-512"


class VerificationStatusEnum(StrEnum):
    """Forensic verification status outcome."""

    VALID = "VALID"
    TAMPERED = "TAMPERED"
    ROOT_MISMATCH = "ROOT_MISMATCH"
    TSA_INVALID = "TSA_INVALID"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    CORRUPTED = "CORRUPTED"


class AuditEntryCreateRequest(BaseModel):
    """Payload to record an attested audit entry in the Merkle ledger."""

    session_id: str = Field(..., min_length=1, max_length=128, description="Target session identifier.")
    actor_id: str = Field(..., min_length=1, max_length=128, description="Primary human user or initiator ID.")
    agent_cert_id: str = Field(..., min_length=1, max_length=128, description="Agent digital certificate ID.")
    action_name: str = Field(..., min_length=1, max_length=128, description="Canonical action or tool name.")
    input_payload: dict[str, str] = Field(default_factory=dict, description="Normalized stringified inputs.")
    output_payload: dict[str, str] = Field(default_factory=dict, description="Normalized stringified outputs.")
    metadata: dict[str, str] = Field(default_factory=dict, description="Forensic metadata tags.")


class AuditEntryNodeResponse(BaseModel):
    """Response representing an attested leaf node in the Merkle ledger."""

    leaf_index: int = Field(..., ge=0, description="0-indexed position in Merkle tree.")
    entry_id: str = Field(..., description="Unique entry ID.")
    leaf_hash: str = Field(..., description="RFC 6962 SHA-256 leaf digest.")
    timestamp: float = Field(..., description="Unix timestamp of registration.")
    details: dict[str, str] = Field(..., description="Indexed metadata details.")


class TsaAnchorRequest(BaseModel):
    """Request to anchor a digest with RFC 3161 Time Stamping Authority."""

    target_digest: Optional[str] = Field(default=None, description="Digest to anchor. If None, anchors current Merkle Root.")
    algorithm: DigestAlgorithmEnum = Field(default=DigestAlgorithmEnum.SHA256, description="Digest algorithm.")


class TsaTimestampTokenResponse(BaseModel):
    """RFC 3161 compliant timestamp token issued by trusted authority."""

    token_id: str = Field(..., description="Unique token ID.")
    digest: str = Field(..., description="Anchored cryptographic digest.")
    digest_algorithm: str = Field(..., description="Algorithm used.")
    timestamp_iso: str = Field(..., description="UTC ISO timestamp.")
    authority_id: str = Field(..., description="Issuing TSA authority identifier.")
    policy_oid: str = Field(..., description="TSA policy OID.")
    serial_number: str = Field(..., description="Unique chronological serial number.")
    signature_hex: str = Field(..., description="HMAC/Cryptographic seal.")


class MerkleProofStepSchema(BaseModel):
    """Step in Merkle inclusion proof."""

    direction: str = Field(..., description="Direction: 'left' or 'right'.")
    hash_value: str = Field(..., description="Sibling hash value.")


class MerkleInclusionProofSchema(BaseModel):
    """Mathematical inclusion proof connecting a leaf to the Merkle root."""

    leaf_index: int = Field(..., ge=0, description="Leaf index.")
    leaf_hash: str = Field(..., description="Leaf SHA-256 hash.")
    root_hash: str = Field(..., description="Expected Merkle root hash.")
    audit_path: list[MerkleProofStepSchema] = Field(..., description="Authentication path.")
    is_valid: bool = Field(..., description="Mathematical validity boolean.")


class EvidenceDossierPackRequest(BaseModel):
    """Request to generate a legal anti-repudiation evidence dossier."""

    entry_id: str = Field(..., min_length=1, description="Target audit entry ID to package.")
    approver_id: Optional[str] = Field(default=None, description="Optional third-party human approver ID.")
    metadata: Optional[dict[str, str]] = Field(default=None, description="Additional legal metadata.")


class EvidenceDossierResponse(BaseModel):
    """Self-contained legal forensic evidence dossier."""

    dossier_id: str = Field(..., description="Unique dossier ID.")
    session_id: str = Field(..., description="Session identifier.")
    actor_id: str = Field(..., description="Initiating actor ID.")
    agent_cert_id: str = Field(..., description="Agent certificate ID.")
    approver_id: Optional[str] = Field(default=None, description="Approver ID.")
    entry_id: str = Field(..., description="Underlying audit entry ID.")
    action_name: str = Field(..., description="Action name.")
    leaf_hash: str = Field(..., description="Leaf hash.")
    merkle_root: str = Field(..., description="Merkle root hash at anchor time.")
    tsa_token: TsaTimestampTokenResponse = Field(..., description="RFC 3161 TSA token.")
    merkle_proof: MerkleInclusionProofSchema = Field(..., description="Mathematical inclusion proof.")
    dossier_signature: str = Field(..., description="Cryptographic seal over the full dossier.")
    created_at: float = Field(..., description="Creation epoch timestamp.")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata tags.")


class EvidenceDossierVerifyRequest(BaseModel):
    """Request to verify an evidence dossier."""

    dossier: EvidenceDossierResponse = Field(..., description="Complete evidence dossier to verify.")


class EvidenceDossierVerifyResponse(BaseModel):
    """Comprehensive verification result of an evidence dossier."""

    is_valid: bool = Field(..., description="Overall validity boolean.")
    status: VerificationStatusEnum = Field(..., description="Verification status.")
    message: str = Field(..., description="Human-readable verification explanation.")
    leaf_match: bool = Field(..., description="Leaf hash consistency boolean.")
    root_match: bool = Field(..., description="Merkle root and inclusion path validity.")
    tsa_match: bool = Field(..., description="RFC 3161 TSA token validity and root anchor match.")
    signature_match: bool = Field(..., description="Enterprise cryptographic seal validity.")


class LedgerStatusResponse(BaseModel):
    """Current state of the append-only Merkle ledger."""

    total_entries: int = Field(..., ge=0, description="Total recorded entries.")
    root_hash: str = Field(..., description="Current Merkle root hash.")
    last_anchored_token_id: Optional[str] = Field(default=None, description="Most recent TSA token ID.")


class LegalAuditMetricsResponse(BaseModel):
    """Telemetry and operational metrics for legal audit subsystem."""

    total_entries: int = Field(..., ge=0, description="Total audit events recorded.")
    total_dossiers_packed: int = Field(..., ge=0, description="Total dossiers generated.")
    total_dossiers_verified: int = Field(..., ge=0, description="Total dossiers evaluated for verification.")
    total_tsa_tokens_issued: int = Field(..., ge=0, description="Total TSA tokens minted.")
