"""Pydantic models for Microsoft Bot Framework activity payloads.

Provides structured, type-safe validation for incoming Bot Framework activities.
All fields are optional with defaults to handle partial payloads gracefully.
``extra="allow"`` ensures forward compatibility with new Bot Framework fields.

[INPUT]
- (none)

[OUTPUT]
- ActivityFrom: The ``from`` field in a Bot Framework activity.
- ActivityConversation: The ``conversation`` field in a Bot Framework activity.
- ActivityMentioned: The ``mentioned`` object inside an entity of type ``menti...
- ActivityEntity: An entity within a Bot Framework activity.
- ActivityAttachment: An attachment within a Bot Framework activity.

[POS]
Pydantic models for Microsoft Bot Framework activity payloads.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ActivityFrom(BaseModel):
    """The ``from`` field in a Bot Framework activity."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    name: str = ""


class ActivityConversation(BaseModel):
    """The ``conversation`` field in a Bot Framework activity."""

    model_config = ConfigDict(extra="allow")

    id: str = ""
    is_group: bool = Field(default=False, alias="isGroup")
    conversation_type: str = Field(default="", alias="conversationType")


class ActivityMentioned(BaseModel):
    """The ``mentioned`` object inside an entity of type ``mention``."""

    model_config = ConfigDict(extra="allow")

    id: str = ""


class ActivityEntity(BaseModel):
    """An entity within a Bot Framework activity."""

    model_config = ConfigDict(extra="allow")

    type: str = ""
    mentioned: ActivityMentioned | None = None


class ActivityAttachment(BaseModel):
    """An attachment within a Bot Framework activity."""

    model_config = ConfigDict(extra="allow")

    content_type: str = Field(default="", alias="contentType")
    content_url: str | None = Field(default=None, alias="contentUrl")
    name: str | None = None
    content: dict[str, object] | None = None


class ActivityRecipient(BaseModel):
    """The ``recipient`` field in a Bot Framework activity."""

    model_config = ConfigDict(extra="allow")

    id: str = ""


class MembersAddedItem(BaseModel):
    """An item in the ``membersAdded`` array."""

    model_config = ConfigDict(extra="allow")

    id: str = ""


class BotActivity(BaseModel):
    """Top-level Bot Framework Activity received via webhook.

    Covers message, invoke, and conversationUpdate activity types.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str = ""
    id: str = ""
    from_user: ActivityFrom | None = Field(default=None, alias="from")
    conversation: ActivityConversation | None = None
    text: str = ""
    service_url: str = Field(default="", alias="serviceUrl")
    reply_to_id: str | None = Field(default=None, alias="replyToId")
    entities: list[ActivityEntity] = Field(default_factory=list)
    attachments: list[ActivityAttachment] = Field(default_factory=list)
    value: dict[str, object] | None = None
    recipient: ActivityRecipient | None = None
    members_added: list[MembersAddedItem] | None = Field(default=None, alias="membersAdded")
