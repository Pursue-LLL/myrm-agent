"""[POS]: app/services/memory/four_tier_fts_service.py
[INPUT]: Harness four_tier_fts engine, dream compactor, models, and server DTO schemas.
[OUTPUT]: FourTierFtsService orchestrating four-tier persistent memory, FTS5 BM25 search, and dream compaction.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    DreamCompactionReport,
    FourTierDreamCompactor,
    FourTierMemoryItem,
    FtsSearchResult,
    MemoryScope,
    SqliteFts5MemoryEngine,
)

from app.schemas.four_tier_fts import (
    DreamCompactionReportDTO,
    FourTierMemoryItemDTO,
    FtsSearchResultDTO,
    RunDreamCompactionRequestDTO,
    SaveFourTierMemoryRequestDTO,
)


class FourTierFtsService:
    """Business service orchestrating four-tier persistent memory and FTS5 search."""

    def __init__(self, base_storage_dir: Path | str | None = None) -> None:
        if base_storage_dir is None:
            self._storage_dir = Path("/tmp/myrm_four_tier_fts")
            self._storage_dir.mkdir(parents=True, exist_ok=True)
        else:
            self._storage_dir = Path(base_storage_dir)

        self._engine = SqliteFts5MemoryEngine(base_storage_dir=self._storage_dir)
        self._compactor = FourTierDreamCompactor(engine=self._engine)

    def save_item(self, request: SaveFourTierMemoryRequestDTO) -> FourTierMemoryItemDTO:
        """Saves or updates a four-tier memory item."""
        try:
            scope_enum = MemoryScope(request.scope)
        except ValueError as err:
            raise ValueError(
                f"Invalid scope '{request.scope}'. Must be one of: {[s.value for s in MemoryScope]}"
            ) from err

        item_id = request.item_id or f"mem_{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        item = FourTierMemoryItem(
            item_id=item_id,
            scope=scope_enum,
            title=request.title,
            content=request.content,
            project_hash=request.project_hash,
            session_id=request.session_id,
            tags=request.tags,
            created_at=now,
            updated_at=now,
        )
        saved = self._engine.save_item(item)
        return self._item_to_dto(saved)

    def get_item(self, item_id: str, project_hash: str = "default") -> FourTierMemoryItemDTO | None:
        """Retrieves a memory item by ID."""
        item = self._engine.get_item(item_id, project_hash=project_hash)
        if item is None:
            return None
        return self._item_to_dto(item)

    def delete_item(self, item_id: str, project_hash: str = "default") -> bool:
        """Deletes a memory item by ID."""
        return self._engine.delete_item(item_id, project_hash=project_hash)

    def list_items(
        self,
        scope: str | None = None,
        project_hash: str = "default",
        session_id: str | None = None,
    ) -> list[FourTierMemoryItemDTO]:
        """Lists items optionally filtered by scope and session ID."""
        scope_enum: MemoryScope | None = None
        if scope:
            try:
                scope_enum = MemoryScope(scope)
            except ValueError as err:
                raise ValueError(f"Invalid scope '{scope}'") from err

        items = self._engine.list_items(
            scope=scope_enum,
            project_hash=project_hash,
            session_id=session_id,
        )
        return [self._item_to_dto(i) for i in items]

    def search_fts(
        self,
        query: str,
        scope: str | None = None,
        project_hash: str = "default",
        limit: int = 10,
    ) -> list[FtsSearchResultDTO]:
        """Performs full-text BM25 search across indexed memory contents."""
        scope_enum: MemoryScope | None = None
        if scope:
            try:
                scope_enum = MemoryScope(scope)
            except ValueError as err:
                raise ValueError(f"Invalid scope '{scope}'") from err

        results = self._engine.search_fts(
            query_text=query,
            project_hash=project_hash,
            scope=scope_enum,
            limit=limit,
        )
        return [self._result_to_dto(r) for r in results]

    def run_dream_compaction(self, request: RunDreamCompactionRequestDTO) -> DreamCompactionReportDTO:
        """Executes a dream cycle compaction merging fragments and purging stale progress memories."""
        report = self._compactor.run_dream_cycle(
            project_hash=request.project_hash,
            purge_progress_days=request.purge_progress_days,
        )
        return self._report_to_dto(report)

    @staticmethod
    def _item_to_dto(item: FourTierMemoryItem) -> FourTierMemoryItemDTO:
        return FourTierMemoryItemDTO(
            item_id=item.item_id,
            scope=item.scope.value,
            title=item.title,
            content=item.content,
            project_hash=item.project_hash,
            session_id=item.session_id,
            tags=list(item.tags),
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    @staticmethod
    def _result_to_dto(result: FtsSearchResult) -> FtsSearchResultDTO:
        return FtsSearchResultDTO(
            item_id=result.item_id,
            scope=result.scope.value,
            project_hash=result.project_hash,
            title=result.title,
            content=result.content,
            snippet=result.snippet,
            bm25_rank=result.bm25_rank,
            updated_at=result.updated_at,
        )

    @staticmethod
    def _report_to_dto(report: DreamCompactionReport) -> DreamCompactionReportDTO:
        return DreamCompactionReportDTO(
            dream_id=report.dream_id,
            scanned_items_count=report.scanned_items_count,
            merged_items_count=report.merged_items_count,
            pruned_items_count=report.pruned_items_count,
            retained_items_count=report.retained_items_count,
            duration_ms=report.duration_ms,
            created_at=report.created_at,
        )


_four_tier_service_instance: FourTierFtsService | None = None


def get_four_tier_fts_service() -> FourTierFtsService:
    """Dependency provider for FourTierFtsService."""
    global _four_tier_service_instance
    if _four_tier_service_instance is None:
        _four_tier_service_instance = FourTierFtsService()
    return _four_tier_service_instance
