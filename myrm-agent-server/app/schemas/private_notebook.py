"""[POS]: app/schemas/private_notebook.py
[INPUT]: Pydantic BaseModel, Field, datetime, and typing primitives.
[OUTPUT]: Request and response DTOs for model private notes, history recall, and context handover.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field


class NoteMetadataDTO(BaseModel):
    """Metadata summary of a single model private note entry."""

    title: str = Field(description="Unique title of the note")
    char_count: int = Field(ge=0, description="Total characters")
    line_count: int = Field(ge=0, description="Total lines")
    updated_at: datetime = Field(description="Last modified timestamp")
    tags: list[str] = Field(default_factory=list, description="Associated categorical tags")


class NoteEntryDTO(BaseModel):
    """Full body representation of a private note."""

    title: str = Field(description="Unique title of the note")
    content: str = Field(description="Markdown content")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Last modified timestamp",
    )
    tags: list[str] = Field(default_factory=list, description="Categorical tags")


class AppendNoteRequestDTO(BaseModel):
    """Request to create or append content to a note."""

    title: str = Field(description="Title of target note")
    content: str = Field(description="Content to append")
    tags: list[str] | None = Field(default=None, description="Optional tags")


class RewriteNoteRequestDTO(BaseModel):
    """Request to overwrite an existing note for human correction or model update."""

    title: str = Field(description="Title of target note")
    content: str = Field(description="New full content")
    tags: list[str] | None = Field(default=None, description="Optional tags")


class NoteSearchResultDTO(BaseModel):
    """Search match outcome across private notes."""

    title: str = Field(description="Matched note title")
    score: float = Field(ge=0.0, le=1.0, description="Relevance score")
    snippet: str = Field(description="Snippet excerpt")


class HistoryContextItemDTO(BaseModel):
    """Archived historical context window summary."""

    context_id: str = Field(description="Historical context identifier")
    title: str = Field(description="Context topic title")
    turn_count: int = Field(ge=0, description="Turn count")
    created_at: datetime = Field(description="Creation timestamp")


class HistoryEntryItemDTO(BaseModel):
    """Individual interaction turn archived under a context window."""

    context_id: str = Field(description="Context window identifier")
    turn_index: int = Field(ge=0, description="Chronological turn index")
    role: str = Field(description="Author role: user, assistant, system, tool")
    content: str = Field(description="Content body")
    created_at: datetime = Field(description="Timestamp")


class RecordTurnRequestDTO(BaseModel):
    """Request to record a turn into current active context."""

    role: str = Field(description="Turn author role")
    content: str = Field(description="Turn message text")


class NewContextRequestDTO(BaseModel):
    """Request to rotate to a clean new context window."""

    summary_reason: str = Field(description="Explicit rationale or state handover notes for switching")
    custom_new_id: str | None = Field(default=None, description="Optional custom new context identifier")


class NewContextResponseDTO(BaseModel):
    """Outcome report for clean context window rotation."""

    new_context_id: str = Field(description="Newly assigned active context identifier")
    previous_context_id: str = Field(description="Archived previous context identifier")
    carried_notes_count: int = Field(ge=0, description="Number of notes carried over")
    status: str = Field(default="ready", description="Operation status")
    message: str = Field(description="Descriptive success message")
