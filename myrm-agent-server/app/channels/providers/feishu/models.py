"""Pydantic models for Feishu/Lark event subscription webhook payloads.

Provides structured, type-safe validation for incoming Feishu events.
All fields are optional with defaults to handle partial payloads gracefully.
``extra="allow"`` ensures forward compatibility with new Feishu API fields.

[INPUT]
- (none)

[OUTPUT]
- FeishuEventHeader: Event header containing event type and metadata.
- FeishuSenderId: Sender ID container with multiple ID types.
- FeishuSender: Message sender information.
- FeishuMention: A single @mention entity in a message.
- FeishuMessage: The message object within an im.message.receive_v1 event.
- FeishuCommentNoticeMeta: Metadata from drive.notice.comment_add_v1 events.
- FeishuCommentEvent: The event payload for drive.notice.comment_add_v1.

[POS]
Pydantic models for Feishu/Lark event subscription webhook payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FeishuEventHeader(BaseModel):
    """Event header containing event type and metadata."""

    model_config = ConfigDict(extra="allow")

    event_type: str = ""
    event_id: str = ""
    create_time: str = ""
    token: str = ""
    app_id: str = ""


class FeishuSenderId(BaseModel):
    """Sender ID container with multiple ID types."""

    model_config = ConfigDict(extra="allow")

    open_id: str = ""
    user_id: str = ""
    union_id: str = ""


class FeishuSender(BaseModel):
    """Message sender information."""

    model_config = ConfigDict(extra="allow")

    sender_id: FeishuSenderId = Field(default_factory=FeishuSenderId)
    sender_type: str = ""
    tenant_key: str = ""


class FeishuMention(BaseModel):
    """A single @mention entity in a message."""

    model_config = ConfigDict(extra="allow")

    key: str = ""
    id: FeishuSenderId = Field(default_factory=FeishuSenderId)
    open_id: str = ""
    name: str = ""
    tenant_key: str = ""


class FeishuMessage(BaseModel):
    """The message object within an im.message.receive_v1 event."""

    model_config = ConfigDict(extra="allow")

    message_id: str = ""
    root_id: str = ""
    parent_id: str = ""
    chat_id: str = ""
    chat_type: str = ""
    message_type: str = Field(default="text", alias="message_type")
    content: str = ""
    mentions: list[FeishuMention] = Field(default_factory=list)


class FeishuMessageEvent(BaseModel):
    """The ``event`` payload for im.message.receive_v1."""

    model_config = ConfigDict(extra="allow")

    sender: FeishuSender = Field(default_factory=FeishuSender)
    message: FeishuMessage = Field(default_factory=FeishuMessage)


class FeishuCardOperator(BaseModel):
    """Operator who triggered a card action."""

    model_config = ConfigDict(extra="allow")

    open_id: str = ""
    user_id: str = ""


class FeishuCardAction(BaseModel):
    """The action payload within a card.action.trigger event."""

    model_config = ConfigDict(extra="allow")

    value: dict[str, object] = Field(default_factory=dict)
    tag: str = ""
    option: str = ""


class FeishuCardEvent(BaseModel):
    """The ``event`` payload for card.action.trigger."""

    model_config = ConfigDict(extra="allow")

    operator: FeishuCardOperator = Field(default_factory=FeishuCardOperator)
    action: FeishuCardAction = Field(default_factory=FeishuCardAction)
    token: str = ""


class FeishuCommentUserId(BaseModel):
    """User ID within a comment notice event."""

    model_config = ConfigDict(extra="allow")

    open_id: str = ""
    user_id: str = ""


class FeishuCommentNoticeMeta(BaseModel):
    """Metadata from ``drive.notice.comment_add_v1`` events.

    Contains the document reference (file_token, file_type) and
    user identifiers for the comment author and target.
    """

    model_config = ConfigDict(extra="allow")

    file_token: str = ""
    file_type: str = ""
    notice_type: str = ""
    from_user_id: FeishuCommentUserId = Field(default_factory=FeishuCommentUserId)
    to_user_id: FeishuCommentUserId = Field(default_factory=FeishuCommentUserId)


class FeishuCommentEvent(BaseModel):
    """The ``event`` payload for ``drive.notice.comment_add_v1``.

    Flat dict with comment identifiers, user routing fields,
    and the structured notice_meta sub-object.
    """

    model_config = ConfigDict(extra="allow")

    event_id: str = ""
    comment_id: str = ""
    reply_id: str = ""
    is_mentioned: bool = False
    timestamp: str = ""
    notice_meta: FeishuCommentNoticeMeta = Field(default_factory=FeishuCommentNoticeMeta)


class FeishuWebhookPayload(BaseModel):
    """Top-level Feishu webhook event payload.

    Handles four event shapes:
    - URL verification: ``challenge`` field present
    - im.message.receive_v1: message events
    - card.action.trigger: interactive card callbacks
    - drive.notice.comment_add_v1: document comment events
    """

    model_config = ConfigDict(extra="allow")

    challenge: str | None = None
    header: FeishuEventHeader = Field(default_factory=FeishuEventHeader)
    event: dict[str, object] = Field(default_factory=dict)
