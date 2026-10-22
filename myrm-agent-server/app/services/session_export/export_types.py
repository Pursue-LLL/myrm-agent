"""Domain types and Pydantic models for Interactive Single-File HTML Export & Gist Share Bridge.

[INPUT] None (Pydantic models)
[OUTPUT] Pure domain types: ExportHtmlOptions, RedactionSummary, InteractiveHtmlExportResult, ShareLinkRequest, ShareLinkResponse.
[POS] app/services/session_export/export_types.py
"""

from pydantic import BaseModel, Field


class RedactedPatternDetail(BaseModel):
    """Detailed summary of a redacted sensitive pattern."""

    pattern_type: str
    count: int
    placeholder: str


class RedactionSummary(BaseModel):
    """Summary of sensitive credentials detected and scrubbed."""

    total_redacted: int = 0
    has_secrets: bool = False
    details: list[RedactedPatternDetail] = Field(default_factory=list)


class ExportHtmlOptions(BaseModel):
    """Options governing standalone HTML compilation."""

    include_thinking: bool = True
    include_tool_calls: bool = True
    enable_redaction: bool = True
    theme: str = "system"  # 'light' | 'dark' | 'system'


class ExportTurnMessage(BaseModel):
    """A sanitized turn message payload for compilation."""

    role: str
    content: str
    created_at: str
    thinking: str | None = None
    tool_calls: list[dict[str, str]] = Field(default_factory=list)


class InteractiveHtmlExportResult(BaseModel):
    """Compiled single-file HTML bundle response."""

    chat_id: str
    title: str
    file_name: str
    html_content: str
    size_bytes: int
    total_messages: int
    redaction_summary: RedactionSummary


class RedactPreviewRequest(BaseModel):
    """Request to preview credential scrubbing on text."""

    text: str


class ShareLinkRequest(BaseModel):
    """Request payload to create a secure time-limited share link."""

    ttl_seconds: int = 7 * 24 * 3600  # Default 7 days
    password: str | None = None


class ShareLinkResponse(BaseModel):
    """Response containing secure share URL and token."""

    chat_id: str
    share_url: str
    share_token: str
    expires_at_unix: int
    is_password_protected: bool
