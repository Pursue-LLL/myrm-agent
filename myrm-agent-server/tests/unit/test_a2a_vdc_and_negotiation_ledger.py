"""Unit tests for Verifiable AI Delegation Credentials (VDC) and Dual-Signed Negotiation Ledger."""

from __future__ import annotations

import time

import pytest

from app.schemas.a2a_vdc import NegotiationTerms
from app.services.a2a.negotiation_ledger import A2ANegotiationLedgerService
from app.services.a2a.vdc_service import VdcService


def test_vdc_issuance_and_offline_verification() -> None:
    """Validate VDC digital signature, validity timeframe, action whitelisting, and financial ceilings."""
    signing_key = "corp_secret_key_9988"
    vdc_service = VdcService(enterprise_key=signing_key)

    # 1. Issue valid VDC
    vdc = vdc_service.issue_vdc(
        issuer_did="did:corp:acme-logistics",
        issuer_name="Acme Logistics Global Ltd.",
        holder_agent_id="agent-procurement-bot",
        holder_name="Senior Procurement Agent",
        max_transaction_amount=50000.0,
        allowed_actions=["quote", "counter_offer", "sign_contract"],
        validity_duration_seconds=3600,
        currency="USD",
        issuer_public_key="acme_master_pubkey_1",
    )
    assert vdc.signature != ""
    assert vdc.max_transaction_amount == 50000.0

    # 2. Verify valid action and amount
    res = vdc_service.verify_vdc(
        vdc=vdc,
        proposed_action="quote",
        proposed_amount=15000.0,
    )
    assert res.is_valid is True
    assert res.failure_reason is None
    assert res.amount_permitted is True
    assert res.action_permitted is True

    # 3. Reject unauthorized action
    unauthorized_res = vdc_service.verify_vdc(
        vdc=vdc,
        proposed_action="liquidate_assets",
        proposed_amount=1000.0,
    )
    assert unauthorized_res.is_valid is False
    assert "not authorized" in str(unauthorized_res.failure_reason)

    # 4. Reject amount exceeding authorized ceiling
    overdraft_res = vdc_service.verify_vdc(
        vdc=vdc,
        proposed_action="quote",
        proposed_amount=60000.0,
    )
    assert overdraft_res.is_valid is False
    assert "exceeds maximum authorized ceiling" in str(overdraft_res.failure_reason)

    # 5. Detect tampered payload
    tampered_vdc = vdc.model_copy()
    tampered_vdc.max_transaction_amount = 99999999.0
    tampered_res = vdc_service.verify_vdc(tampered_vdc)
    assert tampered_res.is_valid is False
    assert "Invalid cryptographic signature" in str(tampered_res.failure_reason)

    # 6. Reject expired credential
    expired_res = vdc_service.verify_vdc(
        vdc=vdc,
        verification_time=time.time() + 10000,
    )
    assert expired_res.is_valid is False
    assert expired_res.is_expired is True


@pytest.mark.asyncio
async def test_dual_signed_negotiation_ledger_and_tamper_detection() -> None:
    """Verify sequential dual-signed negotiation blocks, hash continuity, and non-repudiation."""
    signing_key = "corp_secret_key_common"
    vdc_service = VdcService(enterprise_key=signing_key)
    ledger = A2ANegotiationLedgerService(vdc_service=vdc_service)

    # Issuer A and Agent A
    pubkey_a = "pubkey_corp_a"
    vdc_a = vdc_service.issue_vdc(
        issuer_did="did:corp:corp-alpha",
        issuer_name="Alpha Tech Corp",
        holder_agent_id="agent-alpha-buyer",
        holder_name="Alpha Buyer",
        max_transaction_amount=100000.0,
        allowed_actions=["quote", "counter_offer", "final_contract"],
        issuer_public_key=pubkey_a,
    )

    # Issuer B and Agent B
    pubkey_b = "pubkey_corp_b"
    vdc_b = vdc_service.issue_vdc(
        issuer_did="did:corp:corp-beta",
        issuer_name="Beta Cloud Services",
        holder_agent_id="agent-beta-seller",
        holder_name="Beta Seller",
        max_transaction_amount=100000.0,
        allowed_actions=["quote", "counter_offer", "final_contract"],
        issuer_public_key=pubkey_b,
    )

    session_id = "a2a-sess-comm-001"

    # Step 1: Initial quote
    digest1 = NegotiationTerms.compute_digest(
        action="quote",
        item_description="10x H100 GPU compute hours (monthly retainer)",
        quantity=10,
        unit_price=2500.0,
        total_amount=25000.0,
        currency="USD",
        delivery_deadline="2026-11-01",
    )
    terms1 = NegotiationTerms(
        terms_id="term-01",
        action="quote",
        item_description="10x H100 GPU compute hours (monthly retainer)",
        quantity=10,
        unit_price=2500.0,
        total_amount=25000.0,
        currency="USD",
        delivery_deadline="2026-11-01",
        terms_digest=digest1,
    )
    sig_a_1 = A2ANegotiationLedgerService.sign_terms_digest(pubkey_a, digest1)
    sig_b_1 = A2ANegotiationLedgerService.sign_terms_digest(pubkey_b, digest1)

    block1 = await ledger.append_step(
        session_id=session_id,
        initiator_agent_id="agent-alpha-buyer",
        responder_agent_id="agent-beta-seller",
        initiator_vdc=vdc_a,
        responder_vdc=vdc_b,
        terms=terms1,
        initiator_signature=sig_a_1,
        responder_signature=sig_b_1,
    )
    assert block1.step_index == 0
    assert block1.prev_block_hash == "0" * 64

    # Step 2: Final Contract Acceptance
    digest2 = NegotiationTerms.compute_digest(
        action="final_contract",
        item_description="10x H100 GPU compute hours (monthly retainer, SLA 99.99%)",
        quantity=10,
        unit_price=2400.0,
        total_amount=24000.0,
        currency="USD",
        delivery_deadline="2026-11-01",
    )
    terms2 = NegotiationTerms(
        terms_id="term-02",
        action="final_contract",
        item_description="10x H100 GPU compute hours (monthly retainer, SLA 99.99%)",
        quantity=10,
        unit_price=2400.0,
        total_amount=24000.0,
        currency="USD",
        delivery_deadline="2026-11-01",
        terms_digest=digest2,
    )
    sig_a_2 = A2ANegotiationLedgerService.sign_terms_digest(pubkey_a, digest2)
    sig_b_2 = A2ANegotiationLedgerService.sign_terms_digest(pubkey_b, digest2)

    block2 = await ledger.append_step(
        session_id=session_id,
        initiator_agent_id="agent-beta-seller",
        responder_agent_id="agent-alpha-buyer",
        initiator_vdc=vdc_b,
        responder_vdc=vdc_a,
        terms=terms2,
        initiator_signature=sig_b_2,
        responder_signature=sig_a_2,
    )
    assert block2.step_index == 1
    assert block2.prev_block_hash == block1.block_hash

    # Verify session chain integrity
    intact, err = ledger.verify_session_chain(session_id, pubkey_a, pubkey_b)
    assert intact is True
    assert err is None

    # Export legal audit dossier
    dossier = ledger.export_audit_dossier(
        session_id=session_id,
        initiator_did="did:corp:corp-alpha",
        responder_did="did:corp:corp-beta",
        initiator_public_key=pubkey_a,
        responder_public_key=pubkey_b,
    )
    assert dossier.chain_intact is True
    assert dossier.total_blocks == 2
    assert dossier.final_contract_agreed is True

    # Tamper test: Alter block 1 terms
    ledger._sessions[session_id][0].terms.total_amount = 1.0
    tampered_intact, tampered_err = ledger.verify_session_chain(session_id, pubkey_a, pubkey_b)
    assert tampered_intact is False
    assert "Invalid" in str(tampered_err) or "mismatch" in str(tampered_err) or "tampered" in str(tampered_err)
