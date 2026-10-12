"""Unit tests for Local Action Audit Ledger and Egress Footprint Ledger services."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.services.audit.egress_footprint_ledger import EgressFootprintLedgerService
from app.services.audit.local_action_ledger import LocalActionLedgerService


@pytest.mark.asyncio
async def test_local_action_ledger_hash_chain_and_tamper_detection() -> None:
    """Verify sequential cryptographic hash chain, signature, and tamper detection."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "test_ledger.jsonl"
        signing_key = "test_super_secret_audit_key_2026"
        ledger = LocalActionLedgerService(ledger_file=ledger_path, signing_key=signing_key)

        # 1. Initially empty ledger is healthy
        healthy, err = ledger.verify_chain()
        assert healthy is True
        assert err is None

        # 2. Record multiple local actions
        entry1 = await ledger.record_access(
            agent_id="agent-alice",
            target_entity_type="email",
            target_entity_id="msg-1001",
            entity_hash="hash-email-1001",
            action="read",
            intent_summary="Classify customer inquiry for invoice triage",
            operator_or_model="claude-3-5-sonnet",
        )
        assert entry1.prev_entry_hash == "0" * 64
        assert entry1.entry_hash != ""
        assert entry1.signature != ""

        entry2 = await ledger.record_access(
            agent_id="agent-alice",
            target_entity_type="invoice",
            target_entity_id="inv-2026-001",
            entity_hash="hash-invoice-001",
            action="extract",
            intent_summary="Extract invoice total and vendor bank details",
            operator_or_model="claude-3-5-sonnet",
        )
        assert entry2.prev_entry_hash == entry1.entry_hash

        entry3 = await ledger.record_access(
            agent_id="agent-bob",
            target_entity_type="credential",
            target_entity_id="db-read-secret",
            entity_hash="hash-cred-secret",
            action="read",
            intent_summary="Retrieve read-only DB token",
            operator_or_model="gpt-4o",
        )
        assert entry3.prev_entry_hash == entry2.entry_hash

        # Verify intact chain
        healthy, err = ledger.verify_chain()
        assert healthy is True
        assert err is None

        # 3. Simulate disk reload from persisted JSONL
        reloaded_ledger = LocalActionLedgerService(ledger_file=ledger_path, signing_key=signing_key)
        assert len(reloaded_ledger.query_entries(limit=10)) == 3
        reloaded_healthy, _ = reloaded_ledger.verify_chain()
        assert reloaded_healthy is True

        # 4. Tamper test: modify entry2 content payload directly in memory
        reloaded_ledger._entries[1].action = "tampered_action"
        tampered_healthy, tampered_err = reloaded_ledger.verify_chain()
        assert tampered_healthy is False
        assert "Payload hash mismatch" in str(tampered_err)

        # 5. Tamper test: modify previous hash link
        reloaded_ledger._entries[1].action = "extract"
        reloaded_ledger._entries[2].prev_entry_hash = "f" * 64
        broken_healthy, broken_err = reloaded_ledger.verify_chain()
        assert broken_healthy is False
        assert "Hash continuity broken" in str(broken_err)


@pytest.mark.asyncio
async def test_local_action_ledger_queries_and_inspector_summary() -> None:
    """Verify agent filtering and Privacy Inspector metrics aggregation."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        ledger_path = Path(tmp_dir) / "test_ledger_queries.jsonl"
        ledger = LocalActionLedgerService(ledger_file=ledger_path)

        await ledger.record_access(
            agent_id="agent-finance",
            target_entity_type="email",
            target_entity_id="mail-01",
            entity_hash="h1",
            action="read",
            intent_summary="Inspect email",
            operator_or_model="agent",
        )
        await ledger.record_access(
            agent_id="agent-finance",
            target_entity_type="email",
            target_entity_id="mail-02",
            entity_hash="h2",
            action="draft_reply",
            intent_summary="Draft email reply",
            operator_or_model="agent",
        )
        await ledger.record_access(
            agent_id="agent-hr",
            target_entity_type="id_card",
            target_entity_id="id-99",
            entity_hash="h3",
            action="read",
            intent_summary="Verify employee identity",
            operator_or_model="agent",
        )

        # Filter by agent
        finance_entries = ledger.query_entries(agent_id="agent-finance")
        assert len(finance_entries) == 2
        hr_entries = ledger.query_entries(agent_id="agent-hr")
        assert len(hr_entries) == 1

        # Inspector summary
        summary = ledger.compute_inspector_summary(agent_id="agent-finance")
        assert summary.total_sensitive_entities_read == 2
        assert summary.entity_type_counts.get("email") == 2
        assert summary.total_drafts_created == 1
        assert summary.ledger_chain_healthy is True


@pytest.mark.asyncio
async def test_egress_footprint_ledger_and_destinations() -> None:
    """Verify recording irreversible outbound network facts and destination metrics."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        footprint_path = Path(tmp_dir) / "egress.jsonl"
        ledger = EgressFootprintLedgerService(ledger_file=footprint_path)

        rec1 = await ledger.record_egress(
            agent_id="agent-marketing",
            target_host="api.resend.com",
            target_url="https://api.resend.com/emails",
            content_summary="Sent welcome email to user@domain.com",
            method="POST",
            sensitivity_level="HIGH",
            taint_tags=["external", "pii"],
            approved_by_human=True,
            approval_id="appr-1234",
        )
        assert rec1.is_revocable is False
        assert rec1.approved_by_human is True

        await ledger.record_egress(
            agent_id="agent-marketing",
            target_host="api.resend.com",
            target_url="https://api.resend.com/emails",
            content_summary="Sent newsletter #42",
            method="POST",
            sensitivity_level="MEDIUM",
        )
        await ledger.record_egress(
            agent_id="agent-support",
            target_host="api.slack.com",
            target_url="https://api.slack.com/webhook",
            content_summary="Posted ticket escalation notification",
            method="POST",
            sensitivity_level="LOW",
        )

        # Query footprints
        marketing_footprints = ledger.query_footprints(agent_id="agent-marketing")
        assert len(marketing_footprints) == 2

        # Top contacted hosts
        top_hosts = ledger.get_top_hosts(limit=2)
        assert len(top_hosts) == 2
        assert top_hosts[0]["host"] == "api.resend.com"
        assert top_hosts[0]["count"] == 2

        # Export all
        exported = ledger.export_all()
        assert len(exported) == 3
