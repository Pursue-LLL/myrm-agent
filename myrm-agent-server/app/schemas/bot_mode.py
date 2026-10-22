"""Pydantic V2 schemas for Bot Mode Named Profile Roster & Inter-Bot Mailbox (Item 33).

[INPUT]
- Bot workstation profiles, inter-bot message payloads, and mention dispatch requests.

[OUTPUT]
- Strongly-typed DTOs for named bot rosters, mailbox inboxes, and @mention resolution reports.

[POS]
- Provides typed data contracts for AI colleague workstations, peer-to-peer messaging,
  and @mention addressing.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

ScalarPayload = str | int | float | bool | None


class BotStatusEnum(enum.StrEnum):
    """Execution availability state of a named bot workstation."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"


class MessagePriorityEnum(enum.StrEnum):
    """Urgency level for inter-bot mailbox delivery."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class RegisterBotRequest(BaseModel):
    """Request payload to register a named AI colleague workstation."""

    model_config = ConfigDict(frozen=True)

    bot_id: str = Field(..., min_length=1, description="Unique workstation identifier")
    handle: str = Field(..., min_length=1, description="Unique handle (e.g. @reviewer, @tester)")
    display_name: str = Field(..., min_length=1, description="Human-readable colleague name")
    role_description: str = Field(..., min_length=1, description="Specialized role responsibility")
    avatar_seed: str = Field(..., min_length=1, description="Deterministic avatar generator seed")
    model_tier: str = Field(default="balanced", description="Assigned model execution tier")
    skills: list[str] = Field(default_factory=list, description="Bound skills")
    tools: list[str] = Field(default_factory=list, description="Bound tool access")
    status: BotStatusEnum = Field(default=BotStatusEnum.IDLE, description="Initial availability status")


class BotProfileDTO(BaseModel):
    """Workstation profile details of a registered AI colleague."""

    model_config = ConfigDict(frozen=True)

    bot_id: str
    handle: str
    display_name: str
    role_description: str
    avatar_seed: str
    model_tier: str
    skills: list[str]
    tools: list[str]
    status: BotStatusEnum
    active_task_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class UpdateBotStatusRequest(BaseModel):
    """Payload to update the availability state of a bot."""

    model_config = ConfigDict(frozen=True)

    status: BotStatusEnum
    active_task_id: str | None = None


class SendBotMessageRequest(BaseModel):
    """Payload to deliver a direct message to a colleague bot."""

    model_config = ConfigDict(frozen=True)

    from_bot: str = Field(..., min_length=1, description="Sender bot id or handle")
    to_bot: str = Field(..., min_length=1, description="Recipient bot id or @handle")
    subject: str = Field(..., min_length=1, description="Message subject line")
    body: str = Field(..., min_length=1, description="Message body content")
    priority: MessagePriorityEnum = Field(default=MessagePriorityEnum.NORMAL)
    task_payload: dict[str, ScalarPayload] = Field(
        default_factory=dict,
        description="Structured task arguments",
    )
    thread_id: str | None = Field(None, description="Optional conversation thread identifier")


class BotMessageDTO(BaseModel):
    """Record of a delivered inter-bot direct message."""

    model_config = ConfigDict(frozen=True)

    message_id: str
    from_bot: str
    to_bot: str
    thread_id: str
    subject: str
    body: str
    priority: MessagePriorityEnum
    task_payload: dict[str, ScalarPayload]
    is_read: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class DispatchMentionsRequest(BaseModel):
    """Payload to parse and dispatch @mentions contained in text."""

    model_config = ConfigDict(frozen=True)

    text: str = Field(..., min_length=1, description="Text containing one or more @mentions")
    from_bot: str = Field(..., min_length=1, description="Sender identifier")
    thread_id: str | None = None
    task_payload: dict[str, ScalarPayload] = Field(default_factory=dict)


class MentionDispatchResultDTO(BaseModel):
    """Resolution report for an individual @mention."""

    model_config = ConfigDict(frozen=True)

    dispatched: bool
    target_bot_id: str | None
    target_handle: str | None
    message_id: str | None
    note: str


class MarkReadRequest(BaseModel):
    """Payload to mark messages as read."""

    model_config = ConfigDict(frozen=True)

    message_ids: list[str] = Field(..., min_length=1)


class BotInboxResponse(BaseModel):
    """Mailbox inbox status and message collection for a bot."""

    model_config = ConfigDict(frozen=True)

    bot_id: str
    handle: str
    unread_count: int
    total_count: int
    messages: list[BotMessageDTO]


class BotRosterListResponse(BaseModel):
    """Full roster catalog of registered AI colleague workstations."""

    model_config = ConfigDict(frozen=True)

    bots: list[BotProfileDTO]
    total_count: int
