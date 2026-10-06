"""
[POS] app/services/security/legal_audit_attestation_service.py
[INPUT] myrm_agent_harness.core.security.legal_audit_attestation, app.schemas.legal_audit_attestation
[OUTPUT] LegalAuditAttestationService, get_legal_audit_attestation_service

Thread-safe service managing legal-grade cryptographic audit logs, Merkle tree ledgers,
RFC 3161 TSA timestamps, and evidence dossiers.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from myrm_agent_harness.core.security.legal_audit_attestation import (
    AuditEntryPayload,
    EvidenceDossierSpec,
    LegalAuditAttestationSuite,
    MerkleInclusionProof,
    MerkleProofStep,
    TsaTimestampToken,
)
from myrm_agent_harness.core.security.legal_audit_attestation import (
    DigestAlgorithmEnum as HarnessDigestAlgorithmEnum,
)

from app.schemas.legal_audit_attestation import (
    AuditEntryCreateRequest,
    AuditEntryNodeResponse,
    DigestAlgorithmEnum,
    EvidenceDossierPackRequest,
    EvidenceDossierResponse,
    EvidenceDossierVerifyRequest,
    EvidenceDossierVerifyResponse,
    LedgerStatusResponse,
    LegalAuditMetricsResponse,
    MerkleInclusionProofSchema,
    MerkleProofStepSchema,
    TsaAnchorRequest,
    TsaTimestampTokenResponse,
    VerificationStatusEnum,
)


class LegalAuditAttestationService:
    """Service orchestrating legal-grade cryptographic audit ledgers and RFC 3161 TSA dossiers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._suite = LegalAuditAttestationSuite()
        self._last_anchored_token_id: Optional[str] = None
        self._total_dossiers_packed: int = 0
        self._total_dossiers_verified: int = 0
        self._total_tsa_tokens_issued: int = 0

    def record_entry(self, req: AuditEntryCreateRequest) -> AuditEntryNodeResponse:
        """Record an execution event in the immutable Merkle ledger."""
        entry_id = f"ent-{uuid.uuid4().hex[:12]}"
        now = time.time()
        payload = AuditEntryPayload(
            session_id=req.session_id,
            actor_id=req.actor_id,
            agent_cert_id=req.agent_cert_id,
            action_name=req.action_name,
            input_payload=req.input_payload,
            output_payload=req.output_payload,
            metadata=req.metadata,
            timestamp=now,
        )

        with self._lock:
            node = self._suite.record_audit_event(entry_id, payload)

        return AuditEntryNodeResponse(
            leaf_index=node.leaf_index,
            entry_id=node.entry_id,
            leaf_hash=node.leaf_hash,
            timestamp=node.timestamp,
            details=node.details,
        )

    def anchor_tsa(self, req: TsaAnchorRequest) -> TsaTimestampTokenResponse:
        """Issue an RFC 3161 timestamp token anchoring the Merkle root or given digest."""
        with self._lock:
            algo_map = {
                DigestAlgorithmEnum.SHA256: HarnessDigestAlgorithmEnum.SHA256,
                DigestAlgorithmEnum.SHA384: HarnessDigestAlgorithmEnum.SHA384,
                DigestAlgorithmEnum.SHA512: HarnessDigestAlgorithmEnum.SHA512,
            }
            harness_algo = algo_map.get(req.algorithm, HarnessDigestAlgorithmEnum.SHA256)

            if req.target_digest is not None:
                token = self._suite.tsa_gateway.anchor_digest(req.target_digest, harness_algo)
            else:
                token = self._suite.anchor_merkle_root(harness_algo)

            self._last_anchored_token_id = token.token_id
            self._total_tsa_tokens_issued += 1

        return TsaTimestampTokenResponse(
            token_id=token.token_id,
            digest=token.digest,
            digest_algorithm=token.digest_algorithm,
            timestamp_iso=token.timestamp_iso,
            authority_id=token.authority_id,
            policy_oid=token.policy_oid,
            serial_number=token.serial_number,
            signature_hex=token.signature_hex,
        )

    def pack_dossier(self, req: EvidenceDossierPackRequest) -> Optional[EvidenceDossierResponse]:
        """Pack an existing audit entry into a legal anti-repudiation evidence dossier."""
        with self._lock:
            dossier = self._suite.pack_evidence_dossier(
                entry_id=req.entry_id,
                approver_id=req.approver_id,
                metadata=req.metadata,
            )
            if dossier is None:
                return None

            self._total_dossiers_packed += 1
            self._total_tsa_tokens_issued += 1
            self._last_anchored_token_id = dossier.tsa_token.token_id

        steps = [
            MerkleProofStepSchema(
                direction=step.direction,
                hash_value=step.hash_value,
            )
            for step in dossier.merkle_proof.audit_path
        ]

        tsa_resp = TsaTimestampTokenResponse(
            token_id=dossier.tsa_token.token_id,
            digest=dossier.tsa_token.digest,
            digest_algorithm=dossier.tsa_token.digest_algorithm,
            timestamp_iso=dossier.tsa_token.timestamp_iso,
            authority_id=dossier.tsa_token.authority_id,
            policy_oid=dossier.tsa_token.policy_oid,
            serial_number=dossier.tsa_token.serial_number,
            signature_hex=dossier.tsa_token.signature_hex,
        )

        proof_resp = MerkleInclusionProofSchema(
            leaf_index=dossier.merkle_proof.leaf_index,
            leaf_hash=dossier.merkle_proof.leaf_hash,
            root_hash=dossier.merkle_proof.root_hash,
            audit_path=steps,
            is_valid=dossier.merkle_proof.is_valid,
        )

        return EvidenceDossierResponse(
            dossier_id=dossier.dossier_id,
            session_id=dossier.session_id,
            actor_id=dossier.actor_id,
            agent_cert_id=dossier.agent_cert_id,
            approver_id=dossier.approver_id,
            entry_id=dossier.entry_id,
            action_name=dossier.action_name,
            leaf_hash=dossier.leaf_hash,
            merkle_root=dossier.merkle_root,
            tsa_token=tsa_resp,
            merkle_proof=proof_resp,
            dossier_signature=dossier.dossier_signature,
            created_at=dossier.created_at,
            metadata=dossier.metadata,
        )

    def verify_dossier(self, req: EvidenceDossierVerifyRequest) -> EvidenceDossierVerifyResponse:
        """Verify an evidence dossier independently."""
        with self._lock:
            self._total_dossiers_verified += 1

        d = req.dossier
        tsa_token = TsaTimestampToken(
            token_id=d.tsa_token.token_id,
            digest=d.tsa_token.digest,
            digest_algorithm=d.tsa_token.digest_algorithm,
            timestamp_iso=d.tsa_token.timestamp_iso,
            authority_id=d.tsa_token.authority_id,
            policy_oid=d.tsa_token.policy_oid,
            serial_number=d.tsa_token.serial_number,
            signature_hex=d.tsa_token.signature_hex,
        )

        steps = [
            MerkleProofStep(direction=s.direction, hash_value=s.hash_value)
            for s in d.merkle_proof.audit_path
        ]
        merkle_proof = MerkleInclusionProof(
            leaf_index=d.merkle_proof.leaf_index,
            leaf_hash=d.merkle_proof.leaf_hash,
            root_hash=d.merkle_proof.root_hash,
            audit_path=steps,
            is_valid=d.merkle_proof.is_valid,
        )

        spec = EvidenceDossierSpec(
            dossier_id=d.dossier_id,
            session_id=d.session_id,
            actor_id=d.actor_id,
            agent_cert_id=d.agent_cert_id,
            approver_id=d.approver_id,
            entry_id=d.entry_id,
            action_name=d.action_name,
            leaf_hash=d.leaf_hash,
            merkle_root=d.merkle_root,
            tsa_token=tsa_token,
            merkle_proof=merkle_proof,
            dossier_signature=d.dossier_signature,
            created_at=d.created_at,
            metadata=d.metadata,
        )

        with self._lock:
            res = self._suite.verify_evidence_dossier(spec)

        status_val = VerificationStatusEnum(res.status.value)
        return EvidenceDossierVerifyResponse(
            is_valid=res.is_valid,
            status=status_val,
            message=res.message,
            leaf_match=res.leaf_match,
            root_match=res.root_match,
            tsa_match=res.tsa_match,
            signature_match=res.signature_match,
        )

    def get_ledger_status(self) -> LedgerStatusResponse:
        """Retrieve current status of the Merkle ledger."""
        with self._lock:
            total = self._suite.ledger.total_entries
            root = self._suite.ledger.compute_root_hash()
            last_token = self._last_anchored_token_id

        return LedgerStatusResponse(
            total_entries=total,
            root_hash=root,
            last_anchored_token_id=last_token,
        )

    def get_metrics(self) -> LegalAuditMetricsResponse:
        """Retrieve operational metrics for the legal audit subsystem."""
        with self._lock:
            total_entries = self._suite.ledger.total_entries
            return LegalAuditMetricsResponse(
                total_entries=total_entries,
                total_dossiers_packed=self._total_dossiers_packed,
                total_dossiers_verified=self._total_dossiers_verified,
                total_tsa_tokens_issued=self._total_tsa_tokens_issued,
            )


_SERVICE_INSTANCE: Optional[LegalAuditAttestationService] = None
_SERVICE_LOCK = threading.Lock()


def get_legal_audit_attestation_service() -> LegalAuditAttestationService:
    """Get the singleton instance of LegalAuditAttestationService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = LegalAuditAttestationService()
        return _SERVICE_INSTANCE
