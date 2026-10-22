"""Service mediating Cross-Surface Agent Activity Conversation Bridge (Item 49).

[INPUT]
- IngestActivityRequest, BatchIngestActivityRequest, PruneStalePresencesRequest.

[OUTPUT]
- CrossSurfaceBridgeService managing bounded event ingress and presence projection.

[POS]
- Server-side service layer for cross-surface activity bridge.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

from myrm_agent_harness.agent.sub_agents.cross_surface_bridge import (
    CrossSurfaceActivityBridge,
    CrossSurfaceProjectionSnapshot,
    IngressActivityItem,
    SurfacePresenceSummary,
)

from app.schemas.cross_surface_bridge import (
    ActivityKindEnum,
    BatchIngestActivityRequest,
    CrossSurfaceProjectionResponseDTO,
    IngestActivityRequest,
    IngressActivityItemDTO,
    PresenceStatusEnum,
    PruneStalePresencesRequest,
    PruneStalePresencesResponseDTO,
    SurfaceOriginEnum,
    SurfacePresenceSummaryDTO,
)

logger = logging.getLogger(__name__)


def _item_to_dto(item: IngressActivityItem) -> IngressActivityItemDTO:
    iso_time = datetime.fromtimestamp(item.timestamp, tz=UTC).isoformat()
    return IngressActivityItemDTO(
        activity_id=item.activity_id,
        session_key=item.session_key,
        source_surface=SurfaceOriginEnum(item.source_surface),
        agent_id=item.agent_id,
        activity_kind=ActivityKindEnum(item.activity_kind),
        preview_text=item.preview_text,
        metadata=dict(item.metadata),
        timestamp=iso_time,
    )


def _presence_to_dto(pres: SurfacePresenceSummary) -> SurfacePresenceSummaryDTO:
    iso_time = datetime.fromtimestamp(pres.last_active_at, tz=UTC).isoformat()
    return SurfacePresenceSummaryDTO(
        session_key=pres.session_key,
        source_surface=SurfaceOriginEnum(pres.source_surface),
        agent_id=pres.agent_id,
        status=PresenceStatusEnum(pres.status),
        last_active_at=iso_time,
        recent_activities_count=pres.recent_activities_count,
    )


def _snapshot_to_dto(
    snap: CrossSurfaceProjectionSnapshot,
) -> CrossSurfaceProjectionResponseDTO:
    last_iso = (
        datetime.fromtimestamp(snap.last_ingressed_at, tz=UTC).isoformat()
        if snap.last_ingressed_at is not None
        else None
    )
    return CrossSurfaceProjectionResponseDTO(
        chat_id=snap.chat_id,
        active_presences=[_presence_to_dto(p) for p in snap.active_presences],
        total_ingressed_activities=snap.total_ingressed_activities,
        bounded_recent_activities=[
            _item_to_dto(it) for it in snap.bounded_recent_activities
        ],
        last_ingressed_at=last_iso,
    )


class CrossSurfaceBridgeService:
    """Thread-safe session-scoped service managing Cross-Surface Activity Bridges."""

    def __init__(self, max_recent_items: int = 50) -> None:
        self._max_recent_items = max_recent_items
        self._lock = threading.Lock()
        self._bridges: dict[str, CrossSurfaceActivityBridge] = {}

    def get_or_create_bridge(self, chat_id: str) -> CrossSurfaceActivityBridge:
        """Retrieves or instantiates a session-scoped CrossSurfaceActivityBridge."""
        with self._lock:
            if chat_id not in self._bridges:
                self._bridges[chat_id] = CrossSurfaceActivityBridge(
                    chat_id=chat_id,
                    max_recent_items=self._max_recent_items,
                )
            return self._bridges[chat_id]

    def ingest_activity(
        self, chat_id: str, request: IngestActivityRequest
    ) -> CrossSurfaceProjectionResponseDTO:
        """Ingests a single external activity into the session projection."""
        bridge = self.get_or_create_bridge(chat_id)
        item = IngressActivityItem(
            activity_id=request.activity_id,
            session_key=request.session_key,
            source_surface=request.source_surface.value,
            agent_id=request.agent_id,
            activity_kind=request.activity_kind.value,
            preview_text=request.preview_text,
            metadata=request.metadata,
        )
        snapshot = bridge.ingest_activity(item)
        logger.debug(
            "Ingressed activity %s from %s for chat %s",
            request.activity_id,
            request.source_surface.value,
            chat_id,
        )
        return _snapshot_to_dto(snapshot)

    def ingest_batch(
        self, chat_id: str, request: BatchIngestActivityRequest
    ) -> CrossSurfaceProjectionResponseDTO:
        """Ingests multiple external activities atomically."""
        bridge = self.get_or_create_bridge(chat_id)
        items = [
            IngressActivityItem(
                activity_id=req.activity_id,
                session_key=req.session_key,
                source_surface=req.source_surface.value,
                agent_id=req.agent_id,
                activity_kind=req.activity_kind.value,
                preview_text=req.preview_text,
                metadata=req.metadata,
            )
            for req in request.activities
        ]
        snapshot = bridge.ingest_batch(items)
        return _snapshot_to_dto(snapshot)

    def prune_stale(
        self, chat_id: str, request: PruneStalePresencesRequest
    ) -> PruneStalePresencesResponseDTO:
        """Prunes idle or completed presences for the session."""
        bridge = self.get_or_create_bridge(chat_id)
        pruned_count = bridge.prune_stale_presences(
            max_idle_seconds=request.max_idle_seconds
        )
        snapshot = bridge.get_snapshot()
        return PruneStalePresencesResponseDTO(
            pruned_count=pruned_count,
            updated_snapshot=_snapshot_to_dto(snapshot),
        )

    def get_projection_snapshot(
        self, chat_id: str
    ) -> CrossSurfaceProjectionResponseDTO:
        """Retrieves the current external activity projection for Fleet Canvas."""
        bridge = self.get_or_create_bridge(chat_id)
        return _snapshot_to_dto(bridge.get_snapshot())

    def reset_session(self, chat_id: str) -> CrossSurfaceProjectionResponseDTO:
        """Resets the bridge projection ledger for the chat session."""
        bridge = self.get_or_create_bridge(chat_id)
        bridge.reset()
        return _snapshot_to_dto(bridge.get_snapshot())


# Global singleton instance for server routing
cross_surface_bridge_service = CrossSurfaceBridgeService()
