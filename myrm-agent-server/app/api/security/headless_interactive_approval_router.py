"""API Router for Headless Agent Interactive Approval, Webhook Relay, and Hold-Resume Suite.

[POS] app/api/security/headless_interactive_approval_router.py
[INPUT] fastapi, app.schemas.headless_interactive_approval, app.services.security.headless_interactive_approval_service
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.headless_interactive_approval import (
    CreateHoldTicketRequest,
    FormatStreamHoldNoticeRequest,
    HoldTicketDTO,
    StreamHoldChunkDTO,
    SubmitApprovalDecisionRequest,
    SubmitApprovalDecisionResponse,
    WebhookEndpointConfigRequest,
    WebhookRelayPayloadDTO,
)
from app.services.security.headless_interactive_approval_service import (
    HeadlessInteractiveApprovalService,
    get_headless_approval_service,
)

router = APIRouter(
    prefix="/headless-approval",
    tags=["Security - Headless Agent Interactive Approval & Hold-Resume"],
)


@router.post(
    "/hold-tickets/create",
    response_model=HoldTicketDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create an execution hold ticket and generate approval shortlink",
)
def create_hold_ticket_endpoint(
    request: CreateHoldTicketRequest,
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> HoldTicketDTO:
    """Suspend high-risk headless agent execution and issue ephemeral approval shortlink."""
    return service.create_hold_ticket(request)


@router.get(
    "/hold-tickets/{tx_id}",
    response_model=HoldTicketDTO,
    status_code=status.HTTP_200_OK,
    summary="Query hold ticket details and authorization state",
)
def get_hold_ticket_endpoint(
    tx_id: str,
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> HoldTicketDTO:
    """Fetch status, expiration, and operator decision for an active or past hold ticket."""
    ticket = service.get_ticket(tx_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hold ticket '{tx_id}' not found.",
        )
    return ticket


@router.post(
    "/hold-tickets/{tx_id}/decision",
    response_model=SubmitApprovalDecisionResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit human operator approval or rejection decision",
)
def submit_decision_endpoint(
    tx_id: str,
    request: SubmitApprovalDecisionRequest,
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> SubmitApprovalDecisionResponse:
    """Submit operator decision (APPROVED / REJECTED) and unblock suspended streaming conduit."""
    try:
        return service.submit_decision(tx_id=tx_id, request=request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decision value: {err}",
        ) from err


@router.post(
    "/webhooks/endpoints",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
    summary="Configure an outbound interactive approval webhook endpoint",
)
def register_webhook_endpoint(
    request: WebhookEndpointConfigRequest,
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> dict[str, str]:
    """Register outbound notification webhook destination (e.g. Telegram bot, Feishu webhook)."""
    return service.register_webhook_endpoint(request)


@router.get(
    "/webhooks/endpoints",
    response_model=dict[str, str],
    status_code=status.HTTP_200_OK,
    summary="List all configured approval webhook destinations",
)
def list_webhook_endpoints(
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> dict[str, str]:
    """Retrieve list of active outbound notification webhook endpoints."""
    return service.list_webhook_endpoints()


@router.get(
    "/hold-tickets/{tx_id}/relay-payload",
    response_model=WebhookRelayPayloadDTO,
    status_code=status.HTTP_200_OK,
    summary="Build standardized outbound webhook relay payload for ticket",
)
def get_relay_payload_endpoint(
    tx_id: str,
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> WebhookRelayPayloadDTO:
    """Format structured JSON payload for external push notifications."""
    payload = service.get_relay_payload(tx_id)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hold ticket '{tx_id}' not found.",
        )
    return payload


@router.post(
    "/stream-notice",
    response_model=StreamHoldChunkDTO,
    status_code=status.HTTP_200_OK,
    summary="Format in-stream markdown notice for SSE streaming reasoning",
)
def format_stream_notice_endpoint(
    request: FormatStreamHoldNoticeRequest,
    service: HeadlessInteractiveApprovalService = Depends(
        get_headless_approval_service
    ),
) -> StreamHoldChunkDTO:
    """Format reasoning markdown block for live stream hold/resume injection."""
    try:
        return service.format_stream_notice(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
