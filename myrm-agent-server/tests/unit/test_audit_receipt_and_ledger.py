"""Unit tests for AuditReceipt and AuditLedgerService.

[POS]
Validates cryptographic signing, tamper detection, and hash-chain
integrity of the legal audit ledger suite.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.schemas.audit_receipt import AuditReceipt
from app.services.approvals.audit_ledger import AuditLedgerService


def test_audit_receipt_signing_and_tamper_detection() -> None:
    """Test HMAC-SHA256 signing and tamper detection on AuditReceipt."""
    secret = "test_signing_secret_key"
    receipt = AuditReceipt(
        receipt_id="rcpt-001",
        prev_receipt_hash="0" * 64,
        action_type="WORKSPACE_PHYSICAL_ROLLBACK",
        action_digest="abc123digest",
        snapshot_ref="chk_001",
        operator_id="agent_worker",
        created_at=1700000000.0,
        metadata={"scope": "local"},
    )
    receipt.signature = receipt.sign(secret)

    # 1. Valid signature
    assert receipt.verify_signature(secret) is True

    # 2. Wrong secret
    assert receipt.verify_signature("wrong_secret") is False

    # 3. Tampered payload
    tampered = receipt.model_copy(update={"operator_id": "malicious_user"})
    assert tampered.verify_signature(secret) is False


@pytest.mark.asyncio
async def test_audit_ledger_service_chain_integrity() -> None:
    """Test append-only hash chain linking and verification in AuditLedgerService."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "test_ledger.jsonl"
        service = AuditLedgerService(ledger_file=ledger_path, signing_key="secure_key_123")

        # 1. Record first action
        r1 = await service.record_action(
            action_type="PRE_DESTRUCTIVE_SNAPSHOT",
            action_command="rm -rf build",
            target_assets=["/workspace/build"],
            operator_id="agent-01",
            snapshot_ref="snap-01",
        )
        assert r1.prev_receipt_hash == "0" * 64

        # 2. Record second action
        r2 = await service.record_action(
            action_type="WORKSPACE_PHYSICAL_ROLLBACK",
            action_command="rollback_snapshot:snap-01",
            target_assets=["/workspace"],
            operator_id="user",
            snapshot_ref="snap-01",
        )
        assert r2.prev_receipt_hash == r1.compute_hash()

        # 3. Verify intact chain
        is_valid, err = service.verify_chain()
        assert is_valid is True
        assert err is None

        # 4. List receipts
        recent = service.list_receipts(limit=10)
        assert len(recent) == 2
        assert recent[0].receipt_id == r2.receipt_id

        # 5. Tamper test: corrupt one entry
        service._receipts[0] = service._receipts[0].model_copy(update={"action_type": "FORGED_ACTION"})
        is_valid_after_tamper, err_tamper = service.verify_chain()
        assert is_valid_after_tamper is False
        assert "Tampered signature" in (err_tamper or "")
