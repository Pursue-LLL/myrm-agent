"""FastAPI router for Agent Commerce Dispute & Escrow management.

[INPUT]
- JSON payloads managing autonomous agent escrows, deliverable submissions, and disputes.

[OUTPUT]
- Serialized escrow status, multi-seat arbitration states, and settlement distribution receipts.

[POS]
- REST API layer exposing autonomous commercial escrow and dispute resolution governance.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.commerce_dispute_escrow import (
    CircuitBreakerEvaluationResponse,
    CommitArbitratorVoteRequest,
    CreateEscrowRequest,
    DisputeCaseDto,
    DisputeSettlementResponse,
    EscrowAccountDto,
    EvaluateCircuitBreakerRequest,
    RaiseDisputeRequest,
    ReleaseFundsRequest,
    RevealArbitratorVoteRequest,
    SubmitDeliverableRequest,
)
from app.services.security.commerce_dispute_escrow_service import (
    CommerceDisputeEscrowService,
    get_commerce_dispute_escrow_service,
)

router = APIRouter(
    prefix="/commerce-dispute-escrow",
    tags=["Security: Commerce Dispute Escrow"],
)


@router.post(
    "/escrows",
    response_model=EscrowAccountDto,
    status_code=status.HTTP_201_CREATED,
    summary="Create and fund commercial escrow account",
)
def create_escrow(
    request: CreateEscrowRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> EscrowAccountDto:
    """Initialize a funded escrow agreement between client and provider."""
    try:
        return service.create_escrow(request)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err


@router.get(
    "/escrows/{escrow_id}",
    response_model=EscrowAccountDto,
    summary="Get escrow account details",
)
def get_escrow(
    escrow_id: str,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> EscrowAccountDto:
    """Retrieve current state of an escrow deposit."""
    try:
        return service.get_escrow(escrow_id)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err


@router.post(
    "/escrows/deliver",
    response_model=EscrowAccountDto,
    summary="Submit deliverable proof for escrow",
)
def submit_deliverable(
    request: SubmitDeliverableRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> EscrowAccountDto:
    """Register deliverable artifact hash by provider."""
    try:
        return service.submit_deliverable(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(err)
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err


@router.post(
    "/escrows/release",
    response_model=EscrowAccountDto,
    summary="Release escrowed funds to provider",
)
def release_funds(
    request: ReleaseFundsRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> EscrowAccountDto:
    """Release escrowed capital upon client acceptance."""
    try:
        return service.release_funds(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(err)
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err


@router.post(
    "/escrows/circuit-breaker",
    response_model=CircuitBreakerEvaluationResponse,
    summary="Evaluate trading circuit breakers",
)
def evaluate_circuit_breaker(
    request: EvaluateCircuitBreakerRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> CircuitBreakerEvaluationResponse:
    """Evaluate capital metrics and freeze escrow if limits are violated."""
    try:
        return service.evaluate_circuit_breaker(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err


@router.post(
    "/disputes",
    response_model=DisputeCaseDto,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate arbitration dispute",
)
def raise_dispute(
    request: RaiseDisputeRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> DisputeCaseDto:
    """Raise formal dispute requiring 3-seat commit-reveal arbitration."""
    try:
        return service.raise_dispute(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except PermissionError as err:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(err)
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err


@router.get(
    "/disputes/{dispute_id}",
    response_model=DisputeCaseDto,
    summary="Get dispute case details",
)
def get_dispute(
    dispute_id: str,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> DisputeCaseDto:
    """Retrieve arbitration case details and current voting progress."""
    try:
        return service.get_dispute(dispute_id)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err


@router.post(
    "/disputes/commit",
    response_model=DisputeCaseDto,
    summary="Commit arbitrator vote hash",
)
def commit_vote(
    request: CommitArbitratorVoteRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> DisputeCaseDto:
    """Submit commitment hash for an arbitrator seat."""
    try:
        return service.commit_vote(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except (PermissionError, IndexError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err


@router.post(
    "/disputes/reveal",
    response_model=DisputeCaseDto,
    summary="Reveal committed arbitrator vote",
)
def reveal_vote(
    request: RevealArbitratorVoteRequest,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> DisputeCaseDto:
    """Reveal committed vote and salt."""
    try:
        return service.reveal_vote(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except (PermissionError, IndexError, ValueError) as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err


@router.post(
    "/disputes/{dispute_id}/settle",
    response_model=DisputeSettlementResponse,
    summary="Execute dispute settlement and fund distribution",
)
def settle_dispute(
    dispute_id: str,
    service: CommerceDisputeEscrowService = Depends(
        get_commerce_dispute_escrow_service
    ),
) -> DisputeSettlementResponse:
    """Tally revealed votes and distribute funds accordingly."""
    try:
        return service.settle_dispute(dispute_id)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(err)
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)
        ) from err
