"""Multimodal vision and artifact memory service orchestrating long-term storage and cross-modal search.

[INPUT]
- app.schemas.multimodal_memory
- myrm_agent_harness.toolkits.memory (top-level export)

[OUTPUT]
- MultimodalMemoryService: Domain singleton managing multimodal assets

[POS]
app.services.memory.multimodal_memory_service
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory import (
    ArtifactKind,
    AssetModality,
    MultimodalIngestRequest,
    MultimodalMemoryItem,
    MultimodalMemoryOrchestrator,
    MultimodalSearchHit,
    MultimodalSearchQuery,
)

from app.schemas.multimodal_memory import (
    MultimodalIngestRequestDTO,
    MultimodalMemoryItemDTO,
    MultimodalSearchHitDTO,
    MultimodalSearchRequestDTO,
    MultimodalSearchResponseDTO,
)


class MultimodalMemoryService:
    """Singleton service wrapping Harness MultimodalMemoryOrchestrator."""

    def __init__(self, orchestrator: MultimodalMemoryOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or MultimodalMemoryOrchestrator()

    def ingest_asset(self, payload: MultimodalIngestRequestDTO) -> MultimodalMemoryItemDTO:
        """Ingest a vision asset or sandbox artifact into multimodal memory."""
        modality = AssetModality(payload.modality) if payload.modality in AssetModality._value2member_map_ else AssetModality.ARTIFACT
        kind = ArtifactKind(payload.artifact_kind) if payload.artifact_kind in ArtifactKind._value2member_map_ else ArtifactKind.GENERIC_FILE

        harness_req = MultimodalIngestRequest(
            title=payload.title,
            description=payload.description,
            modality=modality,
            artifact_kind=kind,
            visual_summary=payload.visual_summary,
            file_path=payload.file_path,
            mime_type=payload.mime_type,
            tags=payload.tags,
            session_id=payload.session_id,
            metadata=payload.metadata,
        )

        item: MultimodalMemoryItem = self._orchestrator.ingest_asset(harness_req)
        return self._to_dto(item)

    def search_assets(self, payload: MultimodalSearchRequestDTO) -> MultimodalSearchResponseDTO:
        """Execute cross-modal search against indexed multimodal items."""
        modality_filter = (
            AssetModality(payload.modality_filter)
            if payload.modality_filter and payload.modality_filter in AssetModality._value2member_map_
            else None
        )
        kind_filter = (
            ArtifactKind(payload.artifact_kind_filter)
            if payload.artifact_kind_filter and payload.artifact_kind_filter in ArtifactKind._value2member_map_
            else None
        )

        query = MultimodalSearchQuery(
            query_text=payload.query_text,
            modality_filter=modality_filter,
            artifact_kind_filter=kind_filter,
            session_id=payload.session_id,
            limit=payload.limit,
        )

        hits: list[MultimodalSearchHit] = self._orchestrator.search_assets(query)
        hit_dtos = [
            MultimodalSearchHitDTO(
                item=self._to_dto(hit.item),
                relevance_score=hit.relevance_score,
                matched_modality=hit.matched_modality.value,
                card_preview=hit.card_preview,
            )
            for hit in hits
        ]

        return MultimodalSearchResponseDTO(
            hits=hit_dtos,
            total_matched=len(hit_dtos),
            query_text=payload.query_text,
        )

    def get_asset(self, item_id: str) -> MultimodalMemoryItemDTO | None:
        """Retrieve indexed item by identifier."""
        item = self._orchestrator.get_asset(item_id)
        if item is None:
            return None
        return self._to_dto(item)

    def get_asset_card(self, item_id: str) -> dict[str, str] | None:
        """Retrieve UI presentation card for an indexed asset."""
        return self._orchestrator.get_asset_card(item_id)

    def clear(self) -> None:
        """Reset internal store state."""
        self._orchestrator.clear()

    def _to_dto(self, item: MultimodalMemoryItem) -> MultimodalMemoryItemDTO:
        return MultimodalMemoryItemDTO(
            item_id=item.item_id,
            modality=item.modality.value,
            artifact_kind=item.artifact_kind.value,
            title=item.title,
            description=item.description,
            mime_type=item.mime_type,
            visual_summary=item.visual_summary,
            file_path=item.file_path,
            tags=item.tags,
            session_id=item.session_id,
            created_at=item.created_at,
            metadata=item.metadata,
        )


# Global singleton instance
multimodal_memory_service = MultimodalMemoryService()
