"""[POS]: app/services/memory/private_notebook_service.py
[INPUT]: Harness ModelPrivateNotebookManager, server DTO schemas, and workspace paths.
[OUTPUT]: PrivateNotebookService providing business operations for model scratchpad and context handover.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    ModelPrivateNotebookManager,
)

from app.schemas.private_notebook import (
    AppendNoteRequestDTO,
    HistoryContextItemDTO,
    HistoryEntryItemDTO,
    NewContextRequestDTO,
    NewContextResponseDTO,
    NoteEntryDTO,
    NoteMetadataDTO,
    NoteSearchResultDTO,
    RecordTurnRequestDTO,
    RewriteNoteRequestDTO,
)


class PrivateNotebookService:
    """Business service orchestrating human-inspectable notes, archived histories, and context switching."""

    def __init__(self, workspace_dir: Path | str | None = None) -> None:
        if workspace_dir is None:
            # Fallback to persistent local sandbox directory or system temporary workspace
            base_dir = Path("/tmp/myrm_sandbox_workspace")
            base_dir.mkdir(parents=True, exist_ok=True)
            self._workspace_dir = base_dir
        else:
            self._workspace_dir = Path(workspace_dir)

        self._manager = ModelPrivateNotebookManager(
            workspace_dir=self._workspace_dir,
            initial_context_id="ctx_main",
        )

    @property
    def manager(self) -> ModelPrivateNotebookManager:
        """Accesses the underlying harness manager."""
        return self._manager

    def list_notes(self) -> list[NoteMetadataDTO]:
        """Lists all active markdown notes."""
        metas = self._manager.storage.list_notes()
        return [
            NoteMetadataDTO(
                title=m.title,
                char_count=m.char_count,
                line_count=m.line_count,
                updated_at=m.updated_at,
                tags=m.tags,
            )
            for m in metas
        ]

    def get_note(self, title: str) -> NoteEntryDTO | None:
        """Retrieves a note by title."""
        note = self._manager.storage.read_note(title)
        if note is None:
            return None
        return NoteEntryDTO(
            title=note.title,
            content=note.content,
            updated_at=note.updated_at,
            tags=note.tags,
        )

    def append_note(self, request: AppendNoteRequestDTO) -> NoteEntryDTO:
        """Appends content to an existing or new note."""
        note = self._manager.storage.append_note(
            title=request.title,
            content_to_append=request.content,
            tags=request.tags,
        )
        return NoteEntryDTO(
            title=note.title,
            content=note.content,
            updated_at=note.updated_at,
            tags=note.tags,
        )

    def rewrite_note(self, request: RewriteNoteRequestDTO) -> NoteEntryDTO:
        """Atomically overwrites note for human correction or model refinement."""
        note = self._manager.storage.rewrite_note(
            title=request.title,
            new_content=request.content,
            tags=request.tags,
        )
        return NoteEntryDTO(
            title=note.title,
            content=note.content,
            updated_at=note.updated_at,
            tags=note.tags,
        )

    def delete_note(self, title: str) -> bool:
        """Removes a note file by title."""
        return self._manager.storage.delete_note(title)

    def search_notes(self, query: str) -> list[NoteSearchResultDTO]:
        """Searches notes by keywords."""
        hits = self._manager.storage.search_notes(query)
        return [
            NoteSearchResultDTO(
                title=h.title,
                score=h.score,
                snippet=h.snippet,
            )
            for h in hits
        ]

    def list_contexts(self) -> list[HistoryContextItemDTO]:
        """Lists all archived historical contexts."""
        contexts = self._manager.history.list_contexts()
        return [
            HistoryContextItemDTO(
                context_id=c.context_id,
                title=c.title,
                turn_count=c.turn_count,
                created_at=c.created_at,
            )
            for c in contexts
        ]

    def list_entries(self, context_id: str) -> list[HistoryEntryItemDTO]:
        """Lists turns recorded under context_id."""
        entries = self._manager.history.list_entries(context_id)
        return [
            HistoryEntryItemDTO(
                context_id=e.context_id,
                turn_index=e.turn_index,
                role=e.role,
                content=e.content,
                created_at=e.created_at,
            )
            for e in entries
        ]

    def read_entry(self, context_id: str, turn_index: int) -> HistoryEntryItemDTO | None:
        """Reads a specific turn entry."""
        entry = self._manager.history.read_entry(context_id, turn_index)
        if entry is None:
            return None
        return HistoryEntryItemDTO(
            context_id=entry.context_id,
            turn_index=entry.turn_index,
            role=entry.role,
            content=entry.content,
            created_at=entry.created_at,
        )

    def search_history(self, query: str, max_results: int = 10) -> list[HistoryEntryItemDTO]:
        """Searches history across all contexts."""
        hits = self._manager.history.search_history(query, max_results=max_results)
        return [
            HistoryEntryItemDTO(
                context_id=h.context_id,
                turn_index=h.turn_index,
                role=h.role,
                content=h.content,
                created_at=h.created_at,
            )
            for h in hits
        ]

    def record_turn(self, request: RecordTurnRequestDTO) -> None:
        """Records an ongoing turn into the active context."""
        self._manager.record_turn(request.role, request.content)

    def switch_to_new_context(self, request: NewContextRequestDTO) -> NewContextResponseDTO:
        """Smoothly switches to a clean context while preserving sandbox state and notes."""
        res = self._manager.switch_to_new_context(
            summary_reason=request.summary_reason,
            custom_new_id=request.custom_new_id,
        )
        return NewContextResponseDTO(
            new_context_id=res.new_context_id,
            previous_context_id=res.previous_context_id,
            carried_notes_count=res.carried_notes_count,
            status=res.status,
            message=f"Context successfully rotated. {res.carried_notes_count} notes preserved.",
        )


_service_instance: PrivateNotebookService | None = None


def get_private_notebook_service() -> PrivateNotebookService:
    """Dependency provider returning singleton PrivateNotebookService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PrivateNotebookService()
    return _service_instance
