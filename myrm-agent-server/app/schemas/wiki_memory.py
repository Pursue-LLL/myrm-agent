"""
[POS] app/schemas/wiki_memory.py
[INPUT] pydantic
[OUTPUT] WikiMemoryPageInput, WikiMemoryPageDTO, WikiSearchRequest, WikiSearchMatchDTO, WikiSearchResponse, WikiBacklinkDTO, WikiBacklinkListResponse, WikiAuditCommitDTO, WikiHistoryListResponse, WikiRevertRequest, WikiRevertResponse, WikiRebuildIndexResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WikiMemoryPageInput(BaseModel):
    """Payload to create or update a Markdown memory page."""

    model_config = ConfigDict(extra="forbid")

    page_id: str = Field(..., min_length=1, description="Unique memory page slug or identifier")
    title: str = Field(..., min_length=1, description="Human-readable title of the memory page")
    content: str = Field(..., description="Markdown content body, optionally containing Obsidian [[links]]")
    scope: str = Field(default="global", description="Scope tier: 'global' or 'agent'")
    profile_id: str | None = Field(default=None, description="Profile ID if scoped to a specific agent")
    tags: list[str] = Field(default_factory=list, description="Categorical tags")
    frontmatter: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Custom YAML frontmatter attributes"
    )
    commit_message: str | None = Field(default=None, description="Custom Git commit message")


class WikiMemoryPageDTO(BaseModel):
    """Representation of a persisted Markdown memory page."""

    model_config = ConfigDict(extra="forbid")

    page_id: str
    title: str
    content: str
    scope: str
    profile_id: str | None
    tags: list[str]
    updated_at: float


class WikiSearchRequest(BaseModel):
    """Payload to execute accelerated SQLite FTS5 search across wiki pages."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Search query string")
    scope: str | None = Field(default=None, description="Filter by scope: 'global' or 'agent'")
    profile_id: str | None = Field(default=None, description="Agent profile ID filter")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum returned items")


class WikiSearchMatchDTO(BaseModel):
    """An individual FTS5 full-text search match item."""

    model_config = ConfigDict(extra="forbid")

    page_id: str
    title: str
    snippet: str
    scope: str
    profile_id: str | None
    score: float
    tags: list[str]


class WikiSearchResponse(BaseModel):
    """Response containing search results matching query."""

    model_config = ConfigDict(extra="forbid")

    matches: list[WikiSearchMatchDTO] = Field(default_factory=list)
    total_matched: int = Field(ge=0)


class WikiBacklinkDTO(BaseModel):
    """Obsidian-style backlink indicating an incoming reference to a target page."""

    model_config = ConfigDict(extra="forbid")

    source_page_id: str
    target_page_title: str
    link_text: str
    section: str | None


class WikiBacklinkListResponse(BaseModel):
    """List of incoming backlinks for a given page title."""

    model_config = ConfigDict(extra="forbid")

    target_page_title: str
    backlinks: list[WikiBacklinkDTO] = Field(default_factory=list)
    total_incoming: int = Field(ge=0)


class WikiAuditCommitDTO(BaseModel):
    """A Git commit record tracking memory page modifications."""

    model_config = ConfigDict(extra="forbid")

    commit_hash: str
    message: str
    timestamp: float
    author: str
    files_changed: list[str] = Field(default_factory=list)


class WikiHistoryListResponse(BaseModel):
    """List of recent Git version audit commits."""

    model_config = ConfigDict(extra="forbid")

    commits: list[WikiAuditCommitDTO] = Field(default_factory=list)
    total: int = Field(ge=0)


class WikiRevertRequest(BaseModel):
    """Request payload to revert an erroneous memory commit."""

    model_config = ConfigDict(extra="forbid")

    commit_hash: str = Field(..., min_length=4, description="Git commit hash to revert")


class WikiRevertResponse(BaseModel):
    """Response returned upon Git commit reversion."""

    model_config = ConfigDict(extra="forbid")

    commit_hash: str
    reverted: bool


class WikiRebuildIndexResponse(BaseModel):
    """Audit payload detailing 100% cold recovery of derived SQLite index from Markdown files."""

    model_config = ConfigDict(extra="forbid")

    status: str
    rebuilt_pages: int = Field(ge=0)
    rebuilt_links: int = Field(ge=0)
    duration_ms: float = Field(ge=0.0)
