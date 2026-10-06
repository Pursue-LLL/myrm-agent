"""Anchor highlight search schema definitions.

[INPUT]
None (Pydantic schema definition).

[OUTPUT]
ConversationAnchorHighlightPayload: Sliced text snippet and character boundary offsets.
ConversationAnchorSearchHit: Search result hit equipped with anchor scroll targeting metadata.
ConversationAnchorSearchResponseData: Response data envelope for anchor search API.

[POS]
会话搜索高亮与滚动定位数据契约层。为会话精确短语定位与前端脉冲闪烁高亮（pulse glow）提供结构化 DTO。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConversationAnchorHighlightPayload(BaseModel):
    """Character offsets and surrounding context snippet for target anchor."""

    prefix: str = Field(..., description="Context text slice preceding the matched term")
    matched_text: str = Field(..., description="Exact matched token or phrase")
    suffix: str = Field(..., description="Context text slice following the matched term")
    start_char: int = Field(..., ge=0, description="0-indexed start character offset in original text")
    end_char: int = Field(..., ge=0, description="0-indexed end character offset in original text")
    formatted_snippet: str = Field(..., description="Delimited preview snippet")


class ConversationAnchorSearchHit(BaseModel):
    """Single matching conversation message hit with scroll target anchor."""

    chat_id: str = Field(..., description="Conversation session ID")
    message_id: str = Field(..., description="Target message ID for anchor scroll")
    role: str = Field(..., description="Role of message sender (user or assistant)")
    score: float = Field(..., ge=0.0, le=1.0, description="Exact phrase completeness relevance score")
    highlight: ConversationAnchorHighlightPayload = Field(..., description="Context highlight details")
    chat_title: str | None = Field(None, description="Title of parent conversation")
    sent_at: str | None = Field(None, description="ISO timestamp of message creation")


class ConversationAnchorSearchResponseData(BaseModel):
    """Envelope containing anchor search hits and total count."""

    items: list[ConversationAnchorSearchHit] = Field(..., description="List of matching anchor search hits")
    total: int = Field(..., ge=0, description="Total count of matching hits")
