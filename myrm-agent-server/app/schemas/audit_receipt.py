"""Audit receipt schema and cryptographic tamper-proof validation.

[POS]
Defines the AuditReceipt data model and HMAC-SHA256 signature calculation
for legally binding, tamper-evident high-impact action execution receipts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from pydantic import BaseModel, Field


class AuditReceipt(BaseModel):
    """Tamper-evident audit receipt bound to high-impact actions and CoW snapshots."""

    receipt_id: str = Field(..., description="Unique receipt identifier")
    prev_receipt_hash: str = Field(..., description="SHA-256 hash of the preceding receipt in the ledger chain")
    action_type: str = Field(..., description="High-impact action type identifier")
    action_digest: str = Field(..., description="SHA-256 digest of executed command and affected target assets")
    snapshot_ref: str | None = Field(None, description="Identifier of the associated CoW snapshot or null")
    operator_id: str = Field(..., description="Operator or agent persona identifier initiating the action")
    created_at: float = Field(default_factory=time.time, description="Unix timestamp of receipt generation")
    metadata: dict[str, str] = Field(default_factory=dict, description="Arbitrary contextual key-value attributes")
    signature: str = Field(default="", description="HMAC-SHA256 signature certifying payload authenticity")

    def canonical_payload_bytes(self) -> bytes:
        """Produce deterministic canonical byte representation of the receipt contents."""
        payload: dict[str, object] = {
            "receipt_id": self.receipt_id,
            "prev_receipt_hash": self.prev_receipt_hash,
            "action_type": self.action_type,
            "action_digest": self.action_digest,
            "snapshot_ref": self.snapshot_ref,
            "operator_id": self.operator_id,
            "created_at": self.created_at,
            "metadata": dict(sorted(self.metadata.items())),
        }
        return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    def compute_hash(self) -> str:
        """Compute the cryptographic SHA-256 hash of the receipt payload."""
        return hashlib.sha256(self.canonical_payload_bytes()).hexdigest()

    def sign(self, secret_key: str) -> str:
        """Compute HMAC-SHA256 signature for this receipt and return it."""
        mac = hmac.new(
            secret_key.encode("utf-8"),
            self.canonical_payload_bytes(),
            hashlib.sha256,
        )
        return mac.hexdigest()

    def verify_signature(self, secret_key: str) -> bool:
        """Verify that the receipt signature matches the secret key."""
        if not self.signature:
            return False
        expected_sig = self.sign(secret_key)
        return hmac.compare_digest(self.signature, expected_sig)
