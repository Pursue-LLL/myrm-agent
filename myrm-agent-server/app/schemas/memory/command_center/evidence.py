"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryEvidencePlaybackTurn, MemoryEvidencePlaybackResponse, MemoryRepoCommitDigestItem, MemoryRepoEvidenceResponse

[POS]
Memory command center schemas: evidence playback and repo evidence responses.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class MemoryEvidencePlaybackTurn(BaseModel):
    """Single turn/message in an evidence conversation playback slice."""

    message_id: str
    role: str
    sender_name: str | None = None
    content: str
    sent_at: datetime
    is_target: bool = False
    is_self: bool | None = None


class MemoryEvidencePlaybackResponse(BaseModel):
    """Structured context slice playback response for evidence verification."""

    status: Literal["live_context", "archived_snapshot", "not_found"]
    source_type: Literal["chat", "channel", "unknown"] = "chat"
    source_id: str | None = None
    target_message_id: str | None = None
    channel: str | None = None
    quote_snippet: str | None = None
    author_name: str | None = None
    author_id: str | None = None
    occurred_at: datetime | None = None
    turns: list[MemoryEvidencePlaybackTurn] = Field(default_factory=list)
    is_user_locked: bool = False


class MemoryRepoCommitDigestItem(BaseModel):
    """Single commit summary item for repo evidence."""

    commit_hash: str
    short_hash: str
    author: str
    committed_at: str
    subject: str
    files_changed: list[str] = Field(default_factory=list)


class MemoryRepoEvidenceResponse(BaseModel):
    """Repository history evidence digest response."""

    repo_name: str
    repo_path: str
    current_branch: str
    is_dirty: bool
    recent_commits: list[MemoryRepoCommitDigestItem] = Field(default_factory=list)
    total_commits_examined: int = 0
    extracted_at: str
    is_git_available: bool = True
