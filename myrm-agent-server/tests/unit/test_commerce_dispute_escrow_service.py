"""Unit tests for CommerceDisputeEscrowService in myrm-agent-server."""

from __future__ import annotations

import hashlib

import pytest
from myrm_agent_harness.core.security.commerce_dispute_escrow import (
    CommerceEscrowManager,
)

from app.schemas.commerce_dispute_escrow import (
    CommitArbitratorVoteRequest,
    CreateEscrowRequest,
    EvaluateCircuitBreakerRequest,
    RaiseDisputeRequest,
    ReleaseFundsRequest,
    RevealArbitratorVoteRequest,
    SubmitDeliverableRequest,
    TradingCircuitBreakersDto,
)
from app.services.security.commerce_dispute_escrow_service import (
    CommerceDisputeEscrowService,
    get_commerce_dispute_escrow_service,
)


@pytest.fixture
def service() -> CommerceDisputeEscrowService:
    manager = CommerceEscrowManager()
    return CommerceDisputeEscrowService(manager=manager)


def test_service_escrow_lifecycle(service: CommerceDisputeEscrowService) -> None:
    # 1. Create escrow
    req = CreateEscrowRequest(
        job_id="job_svc_01",
        client_agent_id="client_agent_1",
        provider_agent_id="provider_agent_1",
        strategy_type="PROGRAM",
        amount=600.0,
    )
    escrow = service.create_escrow(req)
    assert escrow.status == "FUNDED"
    assert escrow.amount == 600.0

    # 2. Submit deliverable
    deliver_req = SubmitDeliverableRequest(
        escrow_id=escrow.escrow_id,
        provider_agent_id="provider_agent_1",
        deliverable_hash="0xproof_hash_123",
    )
    delivered = service.submit_deliverable(deliver_req)
    assert delivered.status == "DELIVERED"
    assert delivered.deliverable_hash == "0xproof_hash_123"

    # 3. Release funds
    release_req = ReleaseFundsRequest(
        escrow_id=escrow.escrow_id,
        client_agent_id="client_agent_1",
    )
    released = service.release_funds(release_req)
    assert released.status == "RESOLVED_RELEASED"


def test_service_circuit_breaker(service: CommerceDisputeEscrowService) -> None:
    req = CreateEscrowRequest(
        job_id="job_cex_svc",
        client_agent_id="client_trader",
        provider_agent_id="bot_trader",
        strategy_type="CEX_CAPITAL",
        amount=5000.0,
        circuit_breakers=TradingCircuitBreakersDto(
            max_position_pct=15.0,
            max_daily_loss_pct=5.0,
            max_open_exposure_pct=30.0,
        ),
    )
    escrow = service.create_escrow(req)

    eval_req = EvaluateCircuitBreakerRequest(
        escrow_id=escrow.escrow_id,
        current_daily_loss_pct=8.0,  # Exceeds max 5%
    )
    res = service.evaluate_circuit_breaker(eval_req)
    assert res.triggered is True
    assert "Daily loss limit breached" in str(res.reason)
    assert res.escrow_status == "FROZEN_CIRCUIT_BREAKER"


def test_service_dispute_and_settlement(
    service: CommerceDisputeEscrowService,
) -> None:
    escrow = service.create_escrow(
        CreateEscrowRequest(
            job_id="job_dispute_svc",
            client_agent_id="alice",
            provider_agent_id="bob",
            strategy_type="RUBRIC",
            amount=1000.0,
        )
    )
    service.submit_deliverable(
        SubmitDeliverableRequest(
            escrow_id=escrow.escrow_id,
            provider_agent_id="bob",
            deliverable_hash="0xbad_proof",
        )
    )

    # Raise dispute
    dispute = service.raise_dispute(
        RaiseDisputeRequest(
            escrow_id=escrow.escrow_id,
            initiator_agent_id="alice",
            deposit_amount=50.0,
            arbitrators=["arb_a", "arb_b", "arb_c"],
        )
    )
    assert dispute.status == "VOTING"

    # Commit votes (2 overturn, 1 uphold)
    salt_a, salt_b, salt_c = "sa", "sb", "sc"
    hash_a = hashlib.sha256(f"1:{salt_a}".encode()).hexdigest()
    hash_b = hashlib.sha256(f"1:{salt_b}".encode()).hexdigest()
    hash_c = hashlib.sha256(f"0:{salt_c}".encode()).hexdigest()

    service.commit_vote(
        CommitArbitratorVoteRequest(
            dispute_id=dispute.dispute_id,
            seat_index=0,
            arbitrator_id="arb_a",
            commitment_hash=hash_a,
        )
    )
    service.commit_vote(
        CommitArbitratorVoteRequest(
            dispute_id=dispute.dispute_id,
            seat_index=1,
            arbitrator_id="arb_b",
            commitment_hash=hash_b,
        )
    )
    disp_rev = service.commit_vote(
        CommitArbitratorVoteRequest(
            dispute_id=dispute.dispute_id,
            seat_index=2,
            arbitrator_id="arb_c",
            commitment_hash=hash_c,
        )
    )
    assert disp_rev.status == "REVEAL"

    # Reveal votes
    service.reveal_vote(
        RevealArbitratorVoteRequest(
            dispute_id=dispute.dispute_id,
            seat_index=0,
            arbitrator_id="arb_a",
            vote=1,
            salt=salt_a,
        )
    )
    service.reveal_vote(
        RevealArbitratorVoteRequest(
            dispute_id=dispute.dispute_id,
            seat_index=1,
            arbitrator_id="arb_b",
            vote=1,
            salt=salt_b,
        )
    )
    service.reveal_vote(
        RevealArbitratorVoteRequest(
            dispute_id=dispute.dispute_id,
            seat_index=2,
            arbitrator_id="arb_c",
            vote=0,
            salt=salt_c,
        )
    )

    # Settle
    settlement = service.settle_dispute(dispute.dispute_id)
    assert settlement.dispute.outcome == "OVERTURNED"
    assert settlement.escrow.status == "RESOLVED_REFUNDED"
    assert settlement.refund_to_client == 1000.0 + (50.0 * 0.7)


def test_service_singleton() -> None:
    svc1 = get_commerce_dispute_escrow_service()
    svc2 = get_commerce_dispute_escrow_service()
    assert svc1 is svc2
