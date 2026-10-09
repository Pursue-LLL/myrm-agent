"""[POS]: app/services/memory/revocable_provenance_service.py
[INPUT]: Harness revocable provenance models, stores, engines, and server DTO schemas.
[OUTPUT]: RevocableProvenanceService orchestrating provenance memory storage, atomic revocation, and dream diary inspection.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    DreamDiaryRecorder,
    ProvenanceDreamDiaryEntry,
    ProvenanceMemoryStore,
    ProvenanceMetadata,
    ProvenanceQualifiedMemory,
    RevocableForgetEngine,
)

from app.schemas.revocable_provenance import (
    DreamDiaryEntryDTO,
    ForgetMemoryRequestDTO,
    ForgetResultDTO,
    ProvenanceMetadataDTO,
    ProvenanceQualifiedMemoryDTO,
    RecordDreamDiaryRequestDTO,
    SaveProvenanceMemoryRequestDTO,
)


class RevocableProvenanceService:
    """Business service orchestrating provenance-qualified memory tracking, revocation, and dream diaries."""

    def __init__(self, workspace_dir: Path | str | None = None) -> None:
        if workspace_dir is None:
            base_dir = Path("/tmp/myrm_provenance_workspace")
            base_dir.mkdir(parents=True, exist_ok=True)
            self._workspace_dir = base_dir
        else:
            self._workspace_dir = Path(workspace_dir)

        self._store = ProvenanceMemoryStore(storage_dir=self._workspace_dir / "store")
        self._forget_engine = RevocableForgetEngine(
            store=self._store, tombstone_dir=self._workspace_dir / "tombstones"
        )
        self._diary_recorder = DreamDiaryRecorder(diary_dir=self._workspace_dir / "diaries")

    def save_memory(self, request: SaveProvenanceMemoryRequestDTO) -> ProvenanceQualifiedMemoryDTO:
        """Saves a new provenance-qualified memory, verifying anti-resurrection exclusions."""
        if self._forget_engine.is_excluded(
            session_id=request.session_id,
            message_id=request.message_id,
            statement=request.statement,
        ):
            raise ValueError(
                f"Memory statement '{request.statement}' for source {request.session_id}:{request.message_id} "
                "was previously revoked and is blocked by tombstone exclusion policy."
            )

        memory_id = request.memory_id or f"mem_{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC)
        meta = ProvenanceMetadata(
            session_id=request.session_id,
            message_id=request.message_id,
            turn_index=request.turn_index,
            quote_snippet=request.quote_snippet,
            confidence_score=request.confidence_score,
            extracted_at=now,
        )
        mem = ProvenanceQualifiedMemory(
            memory_id=memory_id,
            statement=request.statement,
            category=request.category,
            provenance=meta,
            is_revoked=False,
            created_at=now,
            updated_at=now,
        )
        saved = self._store.save_memory(mem)
        return self._memory_to_dto(saved)

    def get_memory(self, memory_id: str) -> ProvenanceQualifiedMemoryDTO | None:
        """Retrieves a memory entry by ID."""
        mem = self._store.get_memory(memory_id)
        if mem is None:
            return None
        return self._memory_to_dto(mem)

    def list_memories(self, include_revoked: bool = False) -> list[ProvenanceQualifiedMemoryDTO]:
        """Lists all memories in the store."""
        mems = self._store.list_memories(include_revoked=include_revoked)
        return [self._memory_to_dto(m) for m in mems]

    def find_by_session(
        self, session_id: str, include_revoked: bool = False
    ) -> list[ProvenanceQualifiedMemoryDTO]:
        """Finds all memories derived from a specific source session."""
        mems = self._store.find_by_session(session_id=session_id, include_revoked=include_revoked)
        return [self._memory_to_dto(m) for m in mems]

    def find_by_message(
        self, message_id: str, include_revoked: bool = False
    ) -> list[ProvenanceQualifiedMemoryDTO]:
        """Finds memories originating from a specific message turn."""
        mems = self._store.find_by_message(message_id=message_id, include_revoked=include_revoked)
        return [self._memory_to_dto(m) for m in mems]

    def forget_memory(self, memory_id: str, request: ForgetMemoryRequestDTO) -> ForgetResultDTO:
        """Atomically revokes a memory, registering a tombstone while leaving raw transcripts intact."""
        result = self._forget_engine.forget(memory_id=memory_id, reason=request.reason)
        return ForgetResultDTO(
            memory_id=result.memory_id,
            revoked=result.revoked,
            source_session_id=result.source_session_id,
            source_message_id=result.source_message_id,
            message=result.message,
            transcript_intact=result.transcript_intact,
        )

    def record_dream_diary(self, request: RecordDreamDiaryRequestDTO) -> DreamDiaryEntryDTO:
        """Records a new background dreaming consolidation entry."""
        entry = self._diary_recorder.record_dream(
            agent_id=request.agent_id,
            scanned_turns=request.scanned_turns,
            promoted_memory_ids=request.promoted_memory_ids,
            pruned_duplicates_count=request.pruned_duplicates_count,
            duration_ms=request.duration_ms,
            status=request.status,  # type: ignore[arg-type]
            notes=request.notes,
        )
        return self._diary_to_dto(entry)

    def list_dream_diaries(
        self, agent_id: str | None = None, limit: int = 50
    ) -> list[DreamDiaryEntryDTO]:
        """Lists historical dream diaries for transparent inspection."""
        entries = self._diary_recorder.list_entries(agent_id=agent_id, limit=limit)
        return [self._diary_to_dto(e) for e in entries]

    def _memory_to_dto(self, mem: ProvenanceQualifiedMemory) -> ProvenanceQualifiedMemoryDTO:
        """Converts domain memory model to API DTO."""
        return ProvenanceQualifiedMemoryDTO(
            memory_id=mem.memory_id,
            statement=mem.statement,
            category=mem.category,
            provenance=ProvenanceMetadataDTO(
                session_id=mem.provenance.session_id,
                message_id=mem.provenance.message_id,
                turn_index=mem.provenance.turn_index,
                quote_snippet=mem.provenance.quote_snippet,
                extracted_at=mem.provenance.extracted_at,
                confidence_score=mem.provenance.confidence_score,
            ),
            is_revoked=mem.is_revoked,
            revoked_at=mem.revoked_at,
            revocation_reason=mem.revocation_reason,
            created_at=mem.created_at,
            updated_at=mem.updated_at,
        )

    def _diary_to_dto(self, entry: ProvenanceDreamDiaryEntry) -> DreamDiaryEntryDTO:
        """Converts domain dream diary entry to API DTO."""
        return DreamDiaryEntryDTO(
            dream_id=entry.dream_id,
            agent_id=entry.agent_id,
            scanned_turns=entry.scanned_turns,
            promoted_memory_ids=list(entry.promoted_memory_ids),
            pruned_duplicates_count=entry.pruned_duplicates_count,
            duration_ms=entry.duration_ms,
            status=entry.status,
            notes=entry.notes,
            created_at=entry.created_at,
        )


_revocable_provenance_service_instance: RevocableProvenanceService | None = None


def get_revocable_provenance_service() -> RevocableProvenanceService:
    """Dependency provider yielding the singleton RevocableProvenanceService instance."""
    global _revocable_provenance_service_instance
    if _revocable_provenance_service_instance is None:
        _revocable_provenance_service_instance = RevocableProvenanceService()
    return _revocable_provenance_service_instance
