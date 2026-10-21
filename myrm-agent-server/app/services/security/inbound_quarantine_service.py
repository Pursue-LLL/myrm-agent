"""Service layer managing Inbound Zero-Trust Quarantine & Redaction.

[INPUT]
- Pydantic DTO requests from inbound channel pipelines and quarantine endpoints.

[OUTPUT]
- Redacted safe content for LLM ingestion and secure human release responses.

[POS]
- Bridge between FastAPI routes and Harness InboundQuarantineGate.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.inbound_quarantine import (
    InboundQuarantineGate,
    QuarantineRecord,
    ReleasedSecretInfo,
)

from app.schemas.inbound_quarantine import (
    InspectInboundMessageRequest,
    InspectInboundMessageResponse,
    PurgeQuarantineResponse,
    QuarantineRecordMetadataDto,
    ReleaseQuarantineResponse,
)

logger = logging.getLogger(__name__)


class InboundQuarantineService:
    """Service governing zero-trust sniffing, physical quarantine, and human release."""

    def __init__(self, gate: InboundQuarantineGate | None = None) -> None:
        """Initialize service with gate instance."""
        self._gate = gate or InboundQuarantineGate()

    def inspect_message(
        self, request: InspectInboundMessageRequest
    ) -> InspectInboundMessageResponse:
        """Sniff and quarantine inbound message, returning safe content for LLM ingestion."""
        res = self._gate.inspect_and_quarantine(
            content=request.content,
            channel_type=request.channel_type,
            sender=request.sender,
            recipient=request.recipient,
            ttl_seconds=request.ttl_seconds,
        )
        if res.is_quarantined:
            logger.warning(
                "Inbound message quarantined (id=%s, risks=%s, sender=%s)",
                res.quarantine_id,
                res.detected_risks,
                request.sender,
            )

        return InspectInboundMessageResponse(
            is_quarantined=res.is_quarantined,
            detected_risks=[r.value for r in res.detected_risks],
            safe_content=res.safe_content,
            quarantine_id=res.quarantine_id,
            release_card_url=res.release_card_url,
            expires_at=res.expires_at,
        )

    def get_record_metadata(
        self, quarantine_id: str
    ) -> QuarantineRecordMetadataDto | None:
        """Fetch non-sensitive metadata describing quarantine status."""
        record: QuarantineRecord | None = self._gate.get_quarantine_record(
            quarantine_id
        )
        if record is None:
            return None

        return QuarantineRecordMetadataDto(
            quarantine_id=record.quarantine_id,
            channel_type=record.channel_type,
            sender=record.sender,
            recipient=record.recipient,
            detected_risks=[r.value for r in record.detected_risks],
            status=record.status.value,
            created_at=record.created_at,
            expires_at=record.expires_at,
        )

    def release_quarantine(
        self, quarantine_id: str
    ) -> ReleaseQuarantineResponse | None:
        """Decrypt intercepted content for authenticated human inspection."""
        logger.info("Human release requested for quarantine '%s'", quarantine_id)
        released: ReleasedSecretInfo | None = self._gate.release_quarantine(
            quarantine_id
        )
        if released is None:
            return None

        return ReleaseQuarantineResponse(
            quarantine_id=released.quarantine_id,
            detected_risks=[r.value for r in released.detected_risks],
            original_content=released.original_content,
            released_at=released.released_at,
        )

    def purge_expired(self) -> PurgeQuarantineResponse:
        """Destroy all expired quarantine entries."""
        count = self._gate.purge_expired()
        logger.info("Purged %d expired quarantine records", count)
        return PurgeQuarantineResponse(purged_count=count)


_service_instance: InboundQuarantineService | None = None


def get_inbound_quarantine_service() -> InboundQuarantineService:
    """Dependency injector for InboundQuarantineService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = InboundQuarantineService()
    return _service_instance
