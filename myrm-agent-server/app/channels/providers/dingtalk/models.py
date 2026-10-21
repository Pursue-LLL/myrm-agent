"""Pydantic models for DingTalk robot callback payloads.

Provides structured, type-safe validation for incoming DingTalk events.
All fields are optional with defaults to handle partial payloads gracefully.
``extra="allow"`` ensures forward compatibility with new DingTalk API fields.

[INPUT]
- (none)

[OUTPUT]
- DingTalkTextContent: The ``text`` object in a text-type message.
- DingTalkRichTextItem: A single item in a richText message's richTextList.
- DingTalkRichText: The ``richText`` object in a richText-type message.
- DingTalkMediaContent: The ``content`` object for picture/file-type messages.
- DingTalkAtUser: A single @mention user in the atUsers list.

[POS]
Pydantic models for DingTalk robot callback payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DingTalkTextContent(BaseModel):
    """The ``text`` object in a text-type message."""

    model_config = ConfigDict(extra="allow")

    content: str = ""


class DingTalkRichTextItem(BaseModel):
    """A single item in a richText message's richTextList.

    Each item can be text or picture (with downloadCode for media).
    """

    model_config = ConfigDict(extra="allow")

    type: str = ""
    text: str = ""
    download_code: str = Field(default="", alias="downloadCode")


class DingTalkRichText(BaseModel):
    """The ``richText`` object in a richText-type message."""

    model_config = ConfigDict(extra="allow")

    rich_text_list: list[DingTalkRichTextItem] = Field(default_factory=list, alias="richTextList")


class DingTalkMediaContent(BaseModel):
    """The ``content`` object for picture/file-type messages."""

    model_config = ConfigDict(extra="allow")

    download_code: str = Field(default="", alias="downloadCode")
    file_name: str = Field(default="", alias="fileName")


class DingTalkAtUser(BaseModel):
    """A single @mention user in the atUsers list."""

    model_config = ConfigDict(extra="allow")

    dingtalk_id: str = Field(default="", alias="dingtalkId")
    staff_id: str = Field(default="", alias="staffId")


class DingTalkCallbackPayload(BaseModel):
    """Top-level DingTalk robot callback payload.

    Covers text, richText, picture, and file message types.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    msgtype: str = ""
    sender_staff_id: str = Field(default="", alias="senderStaffId")
    sender_id: str = Field(default="", alias="senderId")
    conversation_id: str = Field(default="", alias="conversationId")
    conversation_type: str = Field(default="", alias="conversationType")
    msg_id: str = Field(default="", alias="msgId")
    text: DingTalkTextContent | None = None
    rich_text: DingTalkRichText | None = Field(default=None, alias="richText")
    content: DingTalkMediaContent | None = None
    at_users: list[DingTalkAtUser] = Field(default_factory=list, alias="atUsers")
    session_webhook: str | None = Field(default=None, alias="sessionWebhook")
    session_webhook_expired_time: int | None = Field(default=None, alias="sessionWebhookExpiredTime")
