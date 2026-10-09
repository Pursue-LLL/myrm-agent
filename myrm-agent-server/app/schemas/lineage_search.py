"""Pydantic schemas for session lineage search and source demotion.

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- SessionMetaDTO, ConversationMessageDTO, AddSessionRequestDTO, AddSessionResponseDTO, AddMessageRequestDTO, AddMessageResponseDTO: session and message ingestion
- LineageSearchRequestDTO, HydratedSessionHitDTO, LineageSearchResponseDTO: lineage search with hydrated hits
- LineageSearchStatsDTO: index statistics including hidden and demoted source counts

[POS]
API contracts of session lineage search, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationMessageDTO(BaseModel):
    """Conversation message data transfer object."""

    message_id: str = Field(description="Unique message identifier")
    session_id: str = Field(description="Parent session identifier")
    role: str = Field(description="Message role: user, assistant, system, or tool")
    content: str = Field(description="Textual content of the message")
    created_at: str = Field(default="", description="ISO 8601 creation timestamp")
    sequence_num: int = Field(default=0, ge=0, description="Monotonic sequence number within session")


class SessionMetaDTO(BaseModel):
    """Session metadata recording provenance and lineage roots."""

    session_id: str = Field(description="Unique session identifier")
    title: str = Field(default="", description="Session title or headline")
    source: str = Field(default="interactive", description="Source category: interactive, cron, subagent, kanban, internal_worker")
    lineage_root_id: str = Field(default="", description="Root session ID shared across compaction generations")
    parent_session_id: str = Field(default="", description="Immediate predecessor session ID if branched or continued")
    model: str = Field(default="", description="Model used in this session")
    started_at: str = Field(default="", description="ISO 8601 started timestamp")


class AddSessionRequestDTO(BaseModel):
    """Payload to register a session."""

    session: SessionMetaDTO = Field(description="Session metadata to record")


class AddSessionResponseDTO(BaseModel):
    """Response confirming session registration."""

    session_id: str = Field(description="Recorded session identifier")
    is_success: bool = Field(description="True if stored successfully")


class AddMessageRequestDTO(BaseModel):
    """Payload to record a message in a session."""

    message: ConversationMessageDTO = Field(description="Message to store and index into FTS5")


class AddMessageResponseDTO(BaseModel):
    """Response confirming message indexing."""

    message_id: str = Field(description="Stored message identifier")
    is_success: bool = Field(description="True if stored and indexed successfully")


class LineageSearchRequestDTO(BaseModel):
    """Parameters for lineage-deduped and demoted discovery search."""

    query: str = Field(min_length=1, description="Search query string")
    limit: int = Field(default=10, ge=1, le=100, description="Max candidate sessions to return")
    max_scan_limit: int = Field(default=300, ge=10, le=1000, description="Over-scan limit before demotion pass")
    include_hidden: bool = Field(default=False, description="True to include internal worker / subagent tasks")
    anchor_window: int = Field(default=5, ge=1, le=20, description="Messages before/after matched anchor for Top 1 hit")
    bookend_count: int = Field(default=3, ge=1, le=10, description="Start/end messages retained for Top 1 hit")


class HydratedSessionHitDTO(BaseModel):
    """Hydrated discovery entry with adaptive window detail and deep link."""

    session_id: str = Field(description="Matched session identifier")
    lineage_root_id: str = Field(description="Canonical lineage root identifier")
    title: str = Field(description="Session title")
    source: str = Field(description="Source provenance category")
    score: float = Field(description="BM25 match score")
    match_message_id: str = Field(description="Specific message ID anchored in match")
    snippet: str = Field(description="Matched text snippet")
    detail_level: str = Field(description="Detail tier: 'full' for Top 1, 'compact' for Top 2-N")
    deep_link: str = Field(description="Direct navigation anchor link (@session:{id}#msg_{mid})")
    window_messages: list[ConversationMessageDTO] = Field(default_factory=list, description="Hydrated messages")
    bookend_start: list[ConversationMessageDTO] = Field(default_factory=list, description="Head messages (Top 1 only)")
    bookend_end: list[ConversationMessageDTO] = Field(default_factory=list, description="Tail messages (Top 1 only)")
    messages_before: int = Field(ge=0, description="Count of messages prior to window")
    messages_after: int = Field(ge=0, description="Count of messages following window")


class LineageSearchResponseDTO(BaseModel):
    """Complete response returned by lineage search."""

    query: str = Field(description="Original search query")
    total_hits: int = Field(ge=0, description="Count of returned sessions")
    results: list[HydratedSessionHitDTO] = Field(default_factory=list, description="Ranked and hydrated hits")


class LineageSearchStatsDTO(BaseModel):
    """Telemetry report of lineage search catalog."""

    total_sessions: int = Field(ge=0, description="Total registered sessions")
    total_messages: int = Field(ge=0, description="Total indexed messages")
    hidden_sources_count: int = Field(ge=0, description="Subagent/kanban worker sessions concealed from search")
    demoted_sources_count: int = Field(ge=0, description="Cron sessions demoted in search ranking")
