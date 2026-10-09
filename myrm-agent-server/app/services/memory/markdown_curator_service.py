"""MarkdownCuratorService, get_markdown_curator_service.

[POS]
app/services/memory/markdown_curator_service.py

[INPUT]
- app.schemas.markdown_curator, myrm_agent_harness.toolkits.memory

[OUTPUT]
- MarkdownCuratorService, get_markdown_curator_service
"""

from __future__ import annotations

import logging
import uuid

from myrm_agent_harness.toolkits.memory import (
    CuratedMemoryCategory,
    CuratedMemoryEntry,
    CuratedMemoryStatus,
    CuratorStudioSummary,
    MarkdownSyncDelta,
    MemoryCuratorStudio,
)

from app.schemas.markdown_curator import (
    AuditEntryRequest,
    CuratedMemoryEntryDTO,
    CurateEntryRequest,
    CuratorStudioSummaryDTO,
    MarkdownSyncRequest,
    MarkdownSyncResponseDTO,
    UpdateCurateEntryRequest,
)

logger = logging.getLogger(__name__)


def _to_entry_dto(entry: CuratedMemoryEntry) -> CuratedMemoryEntryDTO:
    return CuratedMemoryEntryDTO(
        entry_id=entry.entry_id,
        category=entry.category.value,
        title=entry.title,
        content=entry.content,
        confidence=entry.confidence,
        status=entry.status.value,
        tags=list(entry.tags),
        source_session_id=entry.source_session_id,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _to_summary_dto(summary: CuratorStudioSummary) -> CuratorStudioSummaryDTO:
    return CuratorStudioSummaryDTO(
        total_entries=summary.total_entries,
        confirmed_count=summary.confirmed_count,
        pending_count=summary.pending_count,
        rejected_count=summary.rejected_count,
        archived_count=summary.archived_count,
        categories_breakdown=dict(summary.categories_breakdown),
    )


class MarkdownCuratorService:
    """Application service managing curated memory entries and Markdown workspace bi-directional sync."""

    def __init__(self, studio: MemoryCuratorStudio | None = None) -> None:
        self._studio = studio or MemoryCuratorStudio()

    def create_entry(self, req: CurateEntryRequest) -> CuratedMemoryEntryDTO:
        """Create a new curated memory entry in the studio."""
        category_map: dict[str, CuratedMemoryCategory] = {
            "preference": CuratedMemoryCategory.PREFERENCE,
            "fact": CuratedMemoryCategory.FACT,
            "procedure": CuratedMemoryCategory.PROCEDURE,
            "experience": CuratedMemoryCategory.EXPERIENCE,
        }
        status_map: dict[str, CuratedMemoryStatus] = {
            "confirmed": CuratedMemoryStatus.CONFIRMED,
            "pending_confirmation": CuratedMemoryStatus.PENDING_CONFIRMATION,
            "rejected": CuratedMemoryStatus.REJECTED,
            "archived": CuratedMemoryStatus.ARCHIVED,
        }

        cat = category_map.get(req.category.lower(), CuratedMemoryCategory.FACT)
        st = status_map.get(req.status.lower(), CuratedMemoryStatus.CONFIRMED)
        entry_id = f"mem-{uuid.uuid4().hex[:8]}"

        domain_entry = CuratedMemoryEntry(
            entry_id=entry_id,
            category=cat,
            title=req.title,
            content=req.content,
            confidence=req.confidence,
            status=st,
            tags=req.tags,
            source_session_id=req.source_session_id,
        )

        saved = self._studio.add_entry(domain_entry)
        return _to_entry_dto(saved)

    def get_entry(self, entry_id: str) -> CuratedMemoryEntryDTO | None:
        """Fetch an entry by identifier."""
        entry = self._studio.get_entry(entry_id)
        return _to_entry_dto(entry) if entry else None

    def update_entry(
        self,
        entry_id: str,
        req: UpdateCurateEntryRequest,
    ) -> CuratedMemoryEntryDTO:
        """Update an existing curated memory entry."""
        category_map: dict[str, CuratedMemoryCategory] = {
            "preference": CuratedMemoryCategory.PREFERENCE,
            "fact": CuratedMemoryCategory.FACT,
            "procedure": CuratedMemoryCategory.PROCEDURE,
            "experience": CuratedMemoryCategory.EXPERIENCE,
        }
        status_map: dict[str, CuratedMemoryStatus] = {
            "confirmed": CuratedMemoryStatus.CONFIRMED,
            "pending_confirmation": CuratedMemoryStatus.PENDING_CONFIRMATION,
            "rejected": CuratedMemoryStatus.REJECTED,
            "archived": CuratedMemoryStatus.ARCHIVED,
        }

        cat = category_map.get(req.category.lower()) if req.category else None
        st = status_map.get(req.status.lower()) if req.status else None

        updated = self._studio.update_entry(
            entry_id=entry_id,
            title=req.title,
            content=req.content,
            category=cat,
            status=st,
            tags=req.tags,
        )
        return _to_entry_dto(updated)

    def audit_entry(
        self,
        entry_id: str,
        req: AuditEntryRequest,
    ) -> CuratedMemoryEntryDTO:
        """Approve or reject a memory entry candidate."""
        audited = self._studio.audit_entry(entry_id, is_approved=req.is_approved)
        return _to_entry_dto(audited)

    def erase_entry(self, entry_id: str, hard_erase: bool = True) -> bool:
        """Permanently erase or archive a memory entry."""
        return self._studio.erase_entry(entry_id, hard_erase=hard_erase)

    def export_markdown(self, doc_title: str = "Workspace Memory Mirror") -> str:
        """Export active memory entries to formatted Markdown."""
        return self._studio.export_markdown(doc_title=doc_title)

    def sync_from_markdown(self, req: MarkdownSyncRequest) -> MarkdownSyncResponseDTO:
        """Synchronize entries from raw Markdown text into studio store."""
        delta: MarkdownSyncDelta = self._studio.sync_from_markdown(
            req.markdown_text,
            hard_delete=req.hard_delete,
        )
        return MarkdownSyncResponseDTO(
            added_count=len(delta.added_entries),
            updated_count=len(delta.updated_entries),
            deleted_count=len(delta.deleted_entry_ids),
            added_entries=[_to_entry_dto(e) for e in delta.added_entries],
            updated_entries=[_to_entry_dto(e) for e in delta.updated_entries],
            deleted_entry_ids=list(delta.deleted_entry_ids),
        )

    def list_entries(
        self,
        category: str | None = None,
        status: str | None = None,
    ) -> list[CuratedMemoryEntryDTO]:
        """List curated entries with optional filters."""
        category_map: dict[str, CuratedMemoryCategory] = {
            "preference": CuratedMemoryCategory.PREFERENCE,
            "fact": CuratedMemoryCategory.FACT,
            "procedure": CuratedMemoryCategory.PROCEDURE,
            "experience": CuratedMemoryCategory.EXPERIENCE,
        }
        status_map: dict[str, CuratedMemoryStatus] = {
            "confirmed": CuratedMemoryStatus.CONFIRMED,
            "pending_confirmation": CuratedMemoryStatus.PENDING_CONFIRMATION,
            "rejected": CuratedMemoryStatus.REJECTED,
            "archived": CuratedMemoryStatus.ARCHIVED,
        }

        cat = category_map.get(category.lower()) if category else None
        st = status_map.get(status.lower()) if status else None

        items = self._studio.list_entries(category=cat, status=st)
        return [_to_entry_dto(e) for e in items]

    def get_summary(self) -> CuratorStudioSummaryDTO:
        """Fetch summary statistics across curated entries."""
        return _to_summary_dto(self._studio.get_summary())


_instance: MarkdownCuratorService | None = None


def get_markdown_curator_service() -> MarkdownCuratorService:
    """Dependency provider for singleton MarkdownCuratorService."""
    global _instance
    if _instance is None:
        _instance = MarkdownCuratorService()
    return _instance
