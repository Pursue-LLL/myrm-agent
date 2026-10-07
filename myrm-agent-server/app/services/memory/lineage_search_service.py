# [POS]: app/services/memory/lineage_search_service.py
# [INPUT]: SQLite database path, session metadata, messages, query options
# [OUTPUT]: LineageSearchService facade managing lineage dedup, cron demotion, and adaptive hydration

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    ConversationMessage,
    HydratedSessionHit,
    LineageSearchEngine,
    LineageSearchOptions,
    LineageSearchStats,
    SessionMeta,
)

logger = logging.getLogger(__name__)


class LineageSearchService:
    """Service facade coordinating conversation session storage, FTS5 matching,

    lineage root deduplication, cron automation demotion, and adaptive hydration.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        target_path = db_path or ":memory:"
        self._engine = LineageSearchEngine(db_path=target_path)

    @property
    def engine(self) -> LineageSearchEngine:
        return self._engine

    def add_session(self, meta: SessionMeta) -> None:
        """Register or update a session in the catalog."""
        self._engine.add_session(meta)

    def add_message(self, msg: ConversationMessage) -> None:
        """Record and index a conversation message."""
        self._engine.add_message(msg)

    def get_session(self, session_id: str) -> SessionMeta | None:
        """Retrieve session metadata by ID."""
        return self._engine.get_session(session_id)

    def get_messages(self, session_id: str) -> list[ConversationMessage]:
        """Fetch all ordered messages in a session."""
        return self._engine.get_messages(session_id)

    def search(
        self,
        query: str,
        limit: int = 10,
        max_scan_limit: int = 300,
        include_hidden: bool = False,
        anchor_window: int = 5,
        bookend_count: int = 3,
    ) -> list[HydratedSessionHit]:
        """Execute lineage discovery search with PR #19434 recall blindness defense."""
        options = LineageSearchOptions(
            query=query,
            limit=limit,
            max_scan_limit=max_scan_limit,
            include_hidden=include_hidden,
            anchor_window=anchor_window,
            bookend_count=bookend_count,
        )
        return self._engine.search(options)

    def get_stats(self) -> LineageSearchStats:
        """Return operational telemetry."""
        return self._engine.get_stats()

    def close(self) -> None:
        """Close SQLite resources."""
        self._engine.close()


_lineage_search_service_instance: LineageSearchService | None = None


def get_lineage_search_service() -> LineageSearchService:
    """Dependency provider returning singleton LineageSearchService instance."""
    global _lineage_search_service_instance
    if _lineage_search_service_instance is None:
        _lineage_search_service_instance = LineageSearchService()
    return _lineage_search_service_instance
