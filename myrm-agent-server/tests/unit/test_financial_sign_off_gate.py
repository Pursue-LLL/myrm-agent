"""Unit tests for FinancialSignOffGateService and Decision-to-Receipt chain."""

from __future__ import annotations

import pytest

from app.schemas.local_action_audit import (
    ActionSurface,
    BeforeRunPlan,
    FinancialActionDetails,
)
from app.services.approvals.financial_gate import FinancialSignOffGateService
from app.services.audit.egress_footprint_ledger import get_egress_footprint_ledger


@pytest.mark.asyncio
async def test_financial_sign_off_draft_lifecycle_and_decision_to_receipt() -> None:
    """Test full cycle: Draft -> Human Sign-Off -> Execution -> Delivery Receipt Binding."""
    gate = FinancialSignOffGateService()

    # 1. Construct action surface and plan
    fin_details = FinancialActionDetails(
        amount=1250.00,
        currency="USD",
        payee_account="US-BANK-****-5521",
        payee_name="Acme Cloud Services Inc.",
        purpose="Monthly server infrastructure invoice #INV-8890",
    )
    digest = ActionSurface.compute_digest("payment_transfer", fin_details.model_dump_json())
    surface = ActionSurface(
        action_type="payment_transfer",
        financial_details=fin_details,
        action_digest=digest,
    )
    plan = BeforeRunPlan(
        steps=[
            "Step 1: Check account balance",
            "Step 2: Authenticate with Stripe/ACH gateway",
            "Step 3: Transfer $1,250.00 USD to Acme Cloud Services Inc.",
        ],
        risk_assessment="High irreversible financial impact. Funds will be debited immediately.",
        estimated_impact="$1,250.00 debit from operational treasury.",
        fail_closed=True,
    )

    # 2. Create draft
    draft = await gate.create_draft(
        agent_id="agent-procurement",
        action_surface=surface,
        plan=plan,
        session_id="chat-sess-88",
        task_id="task-batch-pay-1",
    )
    assert draft.status == "PENDING_SIGNOFF"
    assert draft.signoff_token is None

    # Check listing
    pending = gate.list_drafts(agent_id="agent-procurement", status="PENDING_SIGNOFF")
    assert len(pending) == 1
    assert pending[0].draft_id == draft.draft_id

    # 3. Human Operator Sign-Off: APPROVE
    approved_draft = await gate.sign_off(
        draft_id=draft.draft_id,
        operator_id="operator-cfo-alice",
        decision="APPROVE",
    )
    assert approved_draft.status == "APPROVED"
    assert approved_draft.operator_id == "operator-cfo-alice"
    assert approved_draft.signoff_token is not None
    assert approved_draft.signed_at is not None

    # Cannot sign-off twice
    with pytest.raises(ValueError, match="cannot sign-off"):
        await gate.sign_off(
            draft_id=draft.draft_id,
            operator_id="operator-cfo-alice",
            decision="APPROVE",
        )

    # 4. Bind post-execution delivery receipt (Completing Decision-to-Receipt three-stage chain)
    delivery_receipt = await gate.bind_delivery_receipt(
        draft_id=draft.draft_id,
        external_reference_id="ach_tx_998877665544",
        delivery_status="SETTLED",
        response_data='{"status": "settled", "tx_id": "ach_tx_998877665544", "fee": 1.25}',
    )
    assert delivery_receipt.delivery_status == "SETTLED"
    assert delivery_receipt.external_reference_id == "ach_tx_998877665544"
    assert delivery_receipt.approval_id == draft.draft_id

    # Verify draft state is now EXECUTED with delivery receipt bound
    final_draft = gate.get_draft(draft.draft_id)
    assert final_draft is not None
    assert final_draft.status == "EXECUTED"
    assert final_draft.delivery_receipt is not None
    assert final_draft.delivery_receipt.delivery_receipt_id == delivery_receipt.delivery_receipt_id

    # Verify egress footprint was automatically recorded
    egress_ledger = get_egress_footprint_ledger()
    footprints = egress_ledger.query_footprints(agent_id="agent-procurement")
    assert any(f.approval_id == draft.draft_id for f in footprints)


@pytest.mark.asyncio
async def test_financial_sign_off_rejection() -> None:
    """Verify operator rejection marks draft REJECTED and forbids receipt binding."""
    gate = FinancialSignOffGateService()

    surface = ActionSurface(
        action_type="payment_transfer",
        financial_details=FinancialActionDetails(
            amount=50000.0,
            currency="USD",
            payee_account="UNKNOWN-ACCT",
            payee_name="Suspicious Vendor",
            purpose="Unverified emergency retainer",
        ),
        action_digest="digest-suspicious",
    )
    plan = BeforeRunPlan(
        steps=["Step 1: Wire funds immediately"],
        risk_assessment="Extreme high risk unknown payee",
        estimated_impact="$50,000.00 wire transfer",
        fail_closed=True,
    )

    draft = await gate.create_draft(
        agent_id="agent-rogue",
        action_surface=surface,
        plan=plan,
    )
    rejected_draft = await gate.sign_off(
        draft_id=draft.draft_id,
        operator_id="operator-sec-bob",
        decision="REJECT",
        rejection_reason="Unverified payee account and suspicious urgency",
    )
    assert rejected_draft.status == "REJECTED"

    # Cannot bind delivery receipt to rejected draft
    with pytest.raises(ValueError, match="Cannot bind delivery receipt"):
        await gate.bind_delivery_receipt(
            draft_id=draft.draft_id,
            external_reference_id="tx_fake",
            delivery_status="DELIVERED",
            response_data="{}",
        )
