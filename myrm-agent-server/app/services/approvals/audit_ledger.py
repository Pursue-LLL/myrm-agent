"""Cryptographic audit ledger service for tamper-evident high-impact actions.

[POS]
Maintains the cryptographic hash chain of AuditReceipts. Guarantees immutable
action auditing and provides chain verification against tampering.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from app.schemas.audit_receipt import AuditReceipt

logger = logging.getLogger(__name__)

_GENESIS_PREV_HASH = "0" * 64
_DEFAULT_SIGNING_KEY = os.getenv("MYRM_AUDIT_SIGNING_KEY", "myrm_internal_audit_secret_key_v1")


class AuditLedgerService:
    """Manages the append-only cryptographic audit receipt ledger."""

    def __init__(self, ledger_file: Path | None = None, signing_key: str = _DEFAULT_SIGNING_KEY) -> None:
        self._ledger_file = ledger_file
        self._signing_key = signing_key
        self._receipts: list[AuditReceipt] = []
        self._lock = asyncio.Lock()
        if self._ledger_file and self._ledger_file.exists():
            self._load_from_disk()

    def _load_from_disk(self) -> None:
        """Load and parse the local audit ledger file."""
        if not self._ledger_file or not self._ledger_file.exists():
            return
        try:
            with open(self._ledger_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        data = json.loads(line)
                        receipt = AuditReceipt(**data)
                        self._receipts.append(receipt)
        except Exception as exc:
            logger.error("Failed to load audit ledger from %s: %s", self._ledger_file, exc)

    def _persist_receipt_sync(self, receipt: AuditReceipt) -> None:
        """Append receipt JSON line to the ledger file."""
        if not self._ledger_file:
            return
        self._ledger_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self._ledger_file, "a", encoding="utf-8") as f:
            f.write(receipt.model_dump_json() + "\n")

    async def record_action(
        self,
        action_type: str,
        action_command: str,
        target_assets: list[str],
        operator_id: str,
        snapshot_ref: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> AuditReceipt:
        """Record a newly executed high-impact action into the tamper-proof ledger."""
        async with self._lock:
            prev_hash = self._receipts[-1].compute_hash() if self._receipts else _GENESIS_PREV_HASH

            # Calculate SHA-256 digest of command and target assets
            digest_input = f"{action_command}|{','.join(sorted(target_assets))}".encode("utf-8")
            action_digest = hashlib.sha256(digest_input).hexdigest()

            receipt = AuditReceipt(
                receipt_id=str(uuid4()),
                prev_receipt_hash=prev_hash,
                action_type=action_type,
                action_digest=action_digest,
                snapshot_ref=snapshot_ref,
                operator_id=operator_id,
                created_at=time.time(),
                metadata=metadata or {},
            )
            # Apply HMAC-SHA256 signature
            receipt.signature = receipt.sign(self._signing_key)
            self._receipts.append(receipt)

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self._persist_receipt_sync, receipt)

            logger.info(
                "Recorded tamper-evident audit receipt: id=%s action=%s snapshot=%s",
                receipt.receipt_id,
                receipt.action_type,
                receipt.snapshot_ref,
            )
            return receipt

    def verify_chain(self) -> tuple[bool, str | None]:
        """Verify the cryptographic integrity of the entire audit chain."""
        expected_prev_hash = _GENESIS_PREV_HASH
        for idx, receipt in enumerate(self._receipts):
            # 1. Verify prev_hash link
            if receipt.prev_receipt_hash != expected_prev_hash:
                err = f"Hash chain broken at index {idx}: expected prev {expected_prev_hash}, got {receipt.prev_receipt_hash}"
                logger.error(err)
                return False, err

            # 2. Verify signature
            if not receipt.verify_signature(self._signing_key):
                err = f"Tampered signature detected at index {idx} (receipt {receipt.receipt_id})"
                logger.error(err)
                return False, err

            expected_prev_hash = receipt.compute_hash()

        return True, None

    def list_receipts(self, limit: int = 50) -> list[AuditReceipt]:
        """Return the most recent receipts, newest first."""
        return list(reversed(self._receipts[-limit:]))


# Global singleton instance
_default_ledger: AuditLedgerService | None = None


def get_audit_ledger() -> AuditLedgerService:
    """Return the global default AuditLedgerService instance."""
    global _default_ledger
    if _default_ledger is None:
        data_dir = Path(os.getenv("MYRM_DATA_DIR", "/tmp/myrm_data"))
        ledger_path = data_dir / "audit" / "audit_ledger.jsonl"
        _default_ledger = AuditLedgerService(ledger_file=ledger_path)
    return _default_ledger
