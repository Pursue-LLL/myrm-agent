"""[POS]: app/api/memory/private_notebook_router.py
[INPUT]: FastAPI APIRouter, Depends, Query, Path, HTTPException, and DTO schemas.
[OUTPUT]: API router exposing endpoints for model private notes, human rectification, and context handover.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

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
from app.services.memory.private_notebook_service import (
    PrivateNotebookService,
    get_private_notebook_service,
)

router = APIRouter(prefix="/notebook", tags=["memory-private-notebook"])


@router.get("/notes", response_model=list[NoteMetadataDTO])
async def list_notes(
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> list[NoteMetadataDTO]:
    """Lists all active private notes with sizes and modification timestamps."""
    return service.list_notes()


@router.get("/notes/search", response_model=list[NoteSearchResultDTO])
async def search_notes(
    q: str = Query(description="Search keyword query"),
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> list[NoteSearchResultDTO]:
    """Searches across notes bodies and titles for relevant snippets."""
    return service.search_notes(q)


@router.get("/notes/{title}", response_model=NoteEntryDTO)
async def get_note(
    title: str,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> NoteEntryDTO:
    """Reads the full markdown body of a private note."""
    note = service.get_note(title)
    if note is None:
        raise HTTPException(status_code=404, detail=f"Note '{title}' not found")
    return note


@router.post("/notes", response_model=NoteEntryDTO)
async def append_note(
    request: AppendNoteRequestDTO,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> NoteEntryDTO:
    """Creates a note or appends content to an existing note."""
    return service.append_note(request)


@router.put("/notes/{title}", response_model=NoteEntryDTO)
async def rewrite_note(
    title: str,
    request: RewriteNoteRequestDTO,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> NoteEntryDTO:
    """Atomically overwrites note for human correction or model refinement."""
    if request.title != title:
        # Align title with path
        request = RewriteNoteRequestDTO(
            title=title,
            content=request.content,
            tags=request.tags,
        )
    return service.rewrite_note(request)


@router.delete("/notes/{title}")
async def delete_note(
    title: str,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> dict[str, object]:
    """Deletes a note file by title."""
    deleted = service.delete_note(title)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Note '{title}' not found or could not be deleted")
    return {"status": "success", "deleted": True, "title": title}


@router.get("/history/contexts", response_model=list[HistoryContextItemDTO])
async def list_contexts(
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> list[HistoryContextItemDTO]:
    """Lists archived past context windows."""
    return service.list_contexts()


@router.get("/history/entries/{context_id}", response_model=list[HistoryEntryItemDTO])
async def list_entries(
    context_id: str,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> list[HistoryEntryItemDTO]:
    """Lists interaction turns under a historical context window."""
    return service.list_entries(context_id)


@router.get("/history/search", response_model=list[HistoryEntryItemDTO])
async def search_history(
    q: str = Query(description="Search keyword query"),
    max_results: int = Query(default=10, ge=1, le=50),
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> list[HistoryEntryItemDTO]:
    """Searches past execution history across all archived contexts."""
    return service.search_history(q, max_results=max_results)


@router.post("/turn")
async def record_turn(
    request: RecordTurnRequestDTO,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> dict[str, object]:
    """Records an ongoing interaction turn into active context history."""
    service.record_turn(request)
    return {"status": "success"}


@router.post("/new-context", response_model=NewContextResponseDTO)
async def switch_to_new_context(
    request: NewContextRequestDTO,
    service: PrivateNotebookService = Depends(get_private_notebook_service),
) -> NewContextResponseDTO:
    """Smoothly switches to a clean context window while preserving notes and sandbox state."""
    return service.switch_to_new_context(request)
