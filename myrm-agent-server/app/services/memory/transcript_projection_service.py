"""Transcript projection and adoption disambiguation service.

[INPUT]
- TranscriptEntryDTO, SessionMessageDTO, BootstrapSessionRequestDTO from schemas.
- SqliteTranscriptProjectionStore, TranscriptAdoptionEngine from harness transcript_projection.

[OUTPUT]
- TranscriptProjectionService providing cold-start projection and duplicate adoption reconciliation.

[POS]
- Server-side domain service for Item 150 SqliteTranscriptProjectionSuite.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.memory.transcript_projection import (
    BootstrapContext,
    SessionMessage,
    SqliteTranscriptProjectionStore,
    TranscriptAdoptionEngine,
    TranscriptEntry,
)

from app.schemas.transcript_projection import (
    AdoptionDecisionDTO,
    BootstrapSessionRequestDTO,
    BootstrapSessionResponseDTO,
    SessionMessageDTO,
    TranscriptEntryDTO,
)

logger = logging.getLogger(__name__)


class TranscriptProjectionService:
    """Service managing SQLite transcript projection and adoption disambiguation."""

    def __init__(self, db_path: str | Path = ":memory:") -> None:
        self._adoption_engine = TranscriptAdoptionEngine(default_tolerance_ms=2000)
        self._store = SqliteTranscriptProjectionStore(
            db_path=db_path,
            adoption_engine=self._adoption_engine,
        )

    @property
    def store(self) -> SqliteTranscriptProjectionStore:
        """Access underlying store instance (primarily for tests and direct seeding)."""
        return self._store

    def append_transcript_entries(self, entries: list[TranscriptEntryDTO]) -> int:
        """Append raw transcript records to the SQLite SSOT table."""
        domain_entries = [
            TranscriptEntry(
                entry_id=e.entry_id,
                session_id=e.session_id,
                seq=e.seq,
                role=e.role,
                content=e.content,
                created_at_ms=e.created_at_ms,
                parent_id=e.parent_id,
            )
            for e in entries
        ]
        self._store.append_transcript_entries(domain_entries)
        return len(domain_entries)

    def ingest_live_messages(self, messages: list[SessionMessageDTO]) -> int:
        """Ingest live host session messages into the working memory store."""
        domain_messages = [
            SessionMessage(
                message_id=m.message_id,
                session_id=m.session_id,
                seq=m.seq,
                role=m.role,
                content=m.content,
                timestamp_ms=m.timestamp_ms,
                transcript_entry_id=m.transcript_entry_id,
            )
            for m in messages
        ]
        self._store.ingest_live_messages(domain_messages)
        return len(domain_messages)

    def bootstrap_session(self, req: BootstrapSessionRequestDTO) -> BootstrapSessionResponseDTO:
        """Execute cold-start transcript projection bootstrap and disambiguate repeated entries."""
        context = BootstrapContext(
            session_id=req.session_id,
            session_key=req.session_key,
            agent_id=req.agent_id,
            tolerance_ms=req.tolerance_ms,
        )
        res = self._store.bootstrap_session(context)
        return BootstrapSessionResponseDTO(
            session_id=res.session_id,
            bootstrapped=res.bootstrapped,
            imported_messages=res.imported_messages,
            already_bootstrapped=res.already_bootstrapped,
            decisions=[
                AdoptionDecisionDTO(
                    message_id=d.message_id,
                    transcript_entry_id=d.transcript_entry_id,
                    status=d.status.value,
                    reason=d.reason,
                )
                for d in res.decisions
            ],
        )

    def get_session_messages(self, session_id: str) -> list[SessionMessageDTO]:
        """Fetch all stored session messages in sequence order."""
        messages = self._store.get_session_messages(session_id)
        return [
            SessionMessageDTO(
                message_id=m.message_id,
                session_id=m.session_id,
                seq=m.seq,
                role=m.role,
                content=m.content,
                timestamp_ms=m.timestamp_ms,
                transcript_entry_id=m.transcript_entry_id,
            )
            for m in messages
        ]

    def get_transcript_entries(self, session_id: str) -> list[TranscriptEntryDTO]:
        """Fetch all stored transcript entries for a session."""
        entries = self._store.get_transcript_entries(session_id)
        return [
            TranscriptEntryDTO(
                entry_id=e.entry_id,
                session_id=e.session_id,
                seq=e.seq,
                role=e.role,
                content=e.content,
                created_at_ms=e.created_at_ms,
                parent_id=e.parent_id,
            )
            for e in entries
        ]


_instance: TranscriptProjectionService | None = None


def get_transcript_projection_service() -> TranscriptProjectionService:
    """Return the singleton instance of TranscriptProjectionService."""
    global _instance
    if _instance is None:
        _instance = TranscriptProjectionService()
    return _instance


def reset_transcript_projection_service() -> None:
    """Reset the singleton instance (used for isolated unit testing)."""
    global _instance
    _instance = None
