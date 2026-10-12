"""FastAPI router for Inbound Zero-Trust Quarantine & Redaction.

[INPUT]
- Web requests inspecting inbound messages, checking quarantine metadata, or requesting release.

[OUTPUT]
- Serialized sanitized content, quarantine records, and decrypted human release cards.

[POS]
- REST API layer providing physical credential quarantine and direct human release endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.inbound_quarantine import (
    InspectInboundMessageRequest,
    InspectInboundMessageResponse,
    PurgeQuarantineResponse,
    QuarantineRecordMetadataDto,
    ReleaseQuarantineResponse,
)
from app.services.security.inbound_quarantine_service import (
    InboundQuarantineService,
    get_inbound_quarantine_service,
)

router = APIRouter(
    prefix="/inbound-quarantine",
    tags=["Security: Inbound Quarantine"],
)


@router.post(
    "/inspect",
    response_model=InspectInboundMessageResponse,
    summary="Inspect and zero-trust redact inbound channel message",
)
def inspect_message(
    request: InspectInboundMessageRequest,
    service: InboundQuarantineService = Depends(get_inbound_quarantine_service),
) -> InspectInboundMessageResponse:
    """Sniff and quarantine inbound message. Raw credentials never enter LLM prompts."""
    return service.inspect_message(request)


@router.get(
    "/records/{quarantine_id}",
    response_model=QuarantineRecordMetadataDto,
    summary="Get quarantine record metadata",
)
def get_record_metadata(
    quarantine_id: str,
    service: InboundQuarantineService = Depends(get_inbound_quarantine_service),
) -> QuarantineRecordMetadataDto:
    """Retrieve non-sensitive metadata for quarantined credential."""
    metadata = service.get_record_metadata(quarantine_id)
    if metadata is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarantine record '{quarantine_id}' not found.",
        )
    return metadata


@router.post(
    "/records/{quarantine_id}/release",
    response_model=ReleaseQuarantineResponse,
    summary="Authorize human release and decryption of quarantined credentials",
)
def release_quarantine(
    quarantine_id: str,
    service: InboundQuarantineService = Depends(get_inbound_quarantine_service),
) -> ReleaseQuarantineResponse:
    """Decrypt and display quarantined credentials strictly for authorized human view."""
    released = service.release_quarantine(quarantine_id)
    if released is None:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=(
                f"Quarantine record '{quarantine_id}' is expired or does not exist."
            ),
        )
    return released


@router.post(
    "/purge",
    response_model=PurgeQuarantineResponse,
    summary="Purge and destroy expired quarantine records",
)
def purge_expired(
    service: InboundQuarantineService = Depends(get_inbound_quarantine_service),
) -> PurgeQuarantineResponse:
    """Clean up expired ephemeral vault entries past their retention TTL."""
    return service.purge_expired()
