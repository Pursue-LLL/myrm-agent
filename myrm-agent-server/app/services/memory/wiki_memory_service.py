"""
[POS] app/services/memory/wiki_memory_service.py
[INPUT] pathlib.Path, app/schemas/wiki_memory.py, myrm_agent_harness.toolkits.memory.wiki_memory
[OUTPUT] WikiMemoryService, get_wiki_memory_service
"""

from __future__ import annotations

import os
from pathlib import Path

from myrm_agent_harness.toolkits.memory.wiki_memory import (
    WikiAuditCommit,
    WikiIndexRebuildResult,
    WikiMemoryEngine,
    WikiMemoryPage,
    WikiScopeLevel,
    WikiSearchMatch,
)

from app.schemas.wiki_memory import (
    WikiAuditCommitDTO,
    WikiBacklinkDTO,
    WikiBacklinkListResponse,
    WikiHistoryListResponse,
    WikiMemoryPageDTO,
    WikiMemoryPageInput,
    WikiRebuildIndexResponse,
    WikiRevertResponse,
    WikiSearchMatchDTO,
    WikiSearchRequest,
    WikiSearchResponse,
)


class WikiMemoryService:
    """Service mediating Markdown-as-SSOT wiki storage, Git audit trails, and SQLite FTS5 indexes."""

    def __init__(self, engine: WikiMemoryEngine | None = None) -> None:
        if engine is not None:
            self._engine = engine
        else:
            base_dir_env = os.getenv("MYRM_WIKI_MEMORY_DIR", ".myrm/wiki_memory_data")
            base_dir = Path(base_dir_env).resolve()
            self._engine = WikiMemoryEngine(base_dir=base_dir)

    def save_page(
        self, req: WikiMemoryPageInput
    ) -> tuple[WikiMemoryPageDTO, WikiAuditCommitDTO | None]:
        """Save Markdown page to SSOT, update derived index, and produce Git version commit."""
        scope_level = WikiScopeLevel.AGENT if req.scope == "agent" else WikiScopeLevel.GLOBAL
        page = WikiMemoryPage(
            page_id=req.page_id,
            title=req.title,
            content=req.content,
            scope=scope_level,
            profile_id=req.profile_id,
            tags=req.tags,
            frontmatter=req.frontmatter,
        )

        commit = self._engine.save_page(page=page, commit_message=req.commit_message)

        saved_page = self._engine.get_page(
            page_id=req.page_id,
            scope=scope_level,
            profile_id=req.profile_id,
        )
        page_dto = self._serialize_page(saved_page or page)
        commit_dto = self._serialize_commit(commit) if commit else None

        return page_dto, commit_dto

    def get_page(
        self,
        page_id: str,
        scope: str = "global",
        profile_id: str | None = None,
    ) -> WikiMemoryPageDTO | None:
        """Fetch memory page directly from physical Markdown source of truth."""
        scope_level = WikiScopeLevel.AGENT if scope == "agent" else WikiScopeLevel.GLOBAL
        page = self._engine.get_page(page_id=page_id, scope=scope_level, profile_id=profile_id)
        if not page:
            return None
        return self._serialize_page(page)

    def delete_page(
        self,
        page_id: str,
        scope: str = "global",
        profile_id: str | None = None,
        commit_message: str | None = None,
    ) -> bool:
        """Delete Markdown page from disk, remove derived index entries, and commit deletion."""
        scope_level = WikiScopeLevel.AGENT if scope == "agent" else WikiScopeLevel.GLOBAL
        return self._engine.delete_page(
            page_id=page_id,
            scope=scope_level,
            profile_id=profile_id,
            commit_message=commit_message,
        )

    def list_pages(
        self,
        scope: str | None = None,
        profile_id: str | None = None,
    ) -> list[WikiMemoryPageDTO]:
        """Scan and list all Markdown pages under specified scope tiers."""
        scope_level = None
        if scope == "global":
            scope_level = WikiScopeLevel.GLOBAL
        elif scope == "agent":
            scope_level = WikiScopeLevel.AGENT

        pages = self._engine.list_pages(scope=scope_level, profile_id=profile_id)
        return [self._serialize_page(p) for p in pages]

    def search(self, req: WikiSearchRequest) -> WikiSearchResponse:
        """Execute accelerated full-text search against the derived SQLite FTS5 index."""
        scope_level = None
        if req.scope == "global":
            scope_level = WikiScopeLevel.GLOBAL
        elif req.scope == "agent":
            scope_level = WikiScopeLevel.AGENT

        matches: list[WikiSearchMatch] = self._engine.search(
            query=req.query,
            scope=scope_level,
            profile_id=req.profile_id,
            limit=req.limit,
        )

        match_dtos = [
            WikiSearchMatchDTO(
                page_id=m.page_id,
                title=m.title,
                snippet=m.snippet,
                scope=m.scope.value,
                profile_id=m.profile_id,
                score=m.score,
                tags=m.tags,
            )
            for m in matches
        ]
        return WikiSearchResponse(matches=match_dtos, total_matched=len(match_dtos))

    def get_backlinks(self, target_page_title: str) -> WikiBacklinkListResponse:
        """Query incoming Obsidian-style backlinks referencing the target title."""
        links = self._engine.get_backlinks(page_title=target_page_title)
        dtos = [
            WikiBacklinkDTO(
                source_page_id=lk.source_page_id,
                target_page_title=lk.target_page_title,
                link_text=lk.link_text,
                section=lk.section,
            )
            for lk in links
        ]
        return WikiBacklinkListResponse(
            target_page_title=target_page_title,
            backlinks=dtos,
            total_incoming=len(dtos),
        )

    def get_history(self, limit: int = 20) -> WikiHistoryListResponse:
        """Retrieve recent Git version audit commits."""
        commits = self._engine.get_history(limit=limit)
        dtos = [self._serialize_commit(c) for c in commits]
        return WikiHistoryListResponse(commits=dtos, total=len(dtos))

    def revert(self, commit_hash: str) -> WikiRevertResponse:
        """Revert a git commit to rollback hallucinated or erroneous memory updates."""
        reverted = self._engine.revert_change(commit_hash=commit_hash)
        return WikiRevertResponse(commit_hash=commit_hash, reverted=reverted)

    def rebuild_index(self) -> WikiRebuildIndexResponse:
        """Reconstruct the derived SQLite FTS5 index 100% idempotently from Markdown files."""
        res: WikiIndexRebuildResult = self._engine.rebuild_derived_index()
        return WikiRebuildIndexResponse(
            status=res.status,
            rebuilt_pages=res.rebuilt_pages,
            rebuilt_links=res.rebuilt_links,
            duration_ms=res.duration_ms,
        )

    @staticmethod
    def _serialize_page(page: WikiMemoryPage) -> WikiMemoryPageDTO:
        return WikiMemoryPageDTO(
            page_id=page.page_id,
            title=page.title,
            content=page.content,
            scope=page.scope.value,
            profile_id=page.profile_id,
            tags=page.tags,
            updated_at=page.updated_at,
        )

    @staticmethod
    def _serialize_commit(c: WikiAuditCommit) -> WikiAuditCommitDTO:
        return WikiAuditCommitDTO(
            commit_hash=c.commit_hash,
            message=c.message,
            timestamp=c.timestamp,
            author=c.author,
            files_changed=c.files_changed,
        )


_SERVICE_INSTANCE: WikiMemoryService | None = None


def get_wiki_memory_service() -> WikiMemoryService:
    """Return singleton instance of WikiMemoryService."""
    global _SERVICE_INSTANCE
    if _SERVICE_INSTANCE is None:
        _SERVICE_INSTANCE = WikiMemoryService()
    return _SERVICE_INSTANCE
