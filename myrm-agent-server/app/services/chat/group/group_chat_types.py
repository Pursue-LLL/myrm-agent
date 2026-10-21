"""Bot Mode Multi-Agent Group Chat & Peer Messaging Types.

[INPUT]
- pydantic: BaseModel, Field
- enum: Enum

[OUTPUT]
- ParticipantRole: Enum of participant roles (human, assistant_bot, system)
- GroupParticipant: Schema representing a participant in a multi-bot room
- GroupMessage: Schema representing a timeline message in group chat
- GroupRoom: Schema representing a multi-bot collaborative room
- GroupRoomCreateRequest: Request model to initialize a group room
- GroupMessageSendRequest: Request model to post message and mention bots
- AgentPeerMessageRequest: Request model for agent-to-agent peer communication (Hermes peer parity)
- AgentPeerMessageResponse: Response model reporting peer message delivery & canonical archiving
- PeerSessionArchive: Schema representing an archived peer interaction in canonical inbox

[POS]
Data contracts for Hermes Agent v0.21.0 Bot Mode and hermes peer parity.
Supports Discord/Slack style multi-bot rooms, Composer @-mention routing, and peer direct messaging.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class ParticipantRole(str, Enum):
    """Role classification of room participants."""

    HUMAN = "human"
    ASSISTANT_BOT = "assistant_bot"
    SYSTEM = "system"


class GroupParticipant(BaseModel):
    """Participant metadata in a group chat room."""

    participant_id: str = Field(..., description="Unique participant or agent profile identifier")
    name: str = Field(..., description="Display name of the participant or bot")
    role: ParticipantRole = Field(default=ParticipantRole.ASSISTANT_BOT, description="Participant role")
    avatar_seed: str = Field(..., description="Seed string used for deterministic avatar rendering")
    avatar_color: str = Field(default="#6366f1", description="Primary deterministic theme color")
    is_avatar_locked: bool = Field(default=True, description="Whether avatar customization is locked")
    description: str | None = Field(default=None, description="Role bio or system persona summary")


class GroupMessage(BaseModel):
    """Message item inside a group room timeline."""

    message_id: str = Field(..., description="Unique message identifier")
    room_id: str = Field(..., description="Parent room identifier")
    sender_id: str = Field(..., description="Sender participant identifier")
    sender_name: str = Field(..., description="Sender display name")
    sender_role: ParticipantRole = Field(..., description="Sender role")
    content: str = Field(..., description="Text content of the message")
    mentioned_agent_ids: list[str] = Field(
        default_factory=list,
        description="List of agent IDs targeted via @-mention in the composer",
    )
    timestamp_epoch_ms: int = Field(..., description="Message creation timestamp in milliseconds")


class GroupRoom(BaseModel):
    """Collaborative multi-bot room entity."""

    room_id: str = Field(..., description="Unique room identifier")
    name: str = Field(..., description="Room title or channel name")
    topic: str = Field(..., description="Discussion topic or goal statement")
    participants: list[GroupParticipant] = Field(
        default_factory=list,
        description="All joined humans and bot participants",
    )
    created_at_epoch_ms: int = Field(..., description="Room creation epoch in milliseconds")
    messages: list[GroupMessage] = Field(
        default_factory=list,
        description="Room timeline messages",
    )


class GroupRoomCreateRequest(BaseModel):
    """Payload to create a new group chat room."""

    name: str = Field(..., min_length=1, max_length=120, description="Room title")
    topic: str = Field(default="General Multi-Agent Collaboration", description="Room topic")
    initial_agent_ids: list[str] = Field(
        default_factory=list,
        description="Agent profiles to invite automatically upon creation",
    )


class GroupMessageSendRequest(BaseModel):
    """Payload to send a message in a group room with optional mentions."""

    sender_id: str = Field(default="user_me", description="Sender identifier")
    content: str = Field(..., min_length=1, description="Message content")
    mentioned_agent_ids: list[str] = Field(
        default_factory=list,
        description="Explicitly mentioned agent profile identifiers",
    )


class AgentPeerMessageRequest(BaseModel):
    """Payload for agent-to-agent direct consultation (hermes peer parity)."""

    sender_agent_id: str = Field(..., description="Calling source agent identifier")
    target_agent_id: str = Field(..., description="Destination peer agent identifier")
    content: str = Field(..., min_length=1, description="Direct query or consultation prompt")
    context_task_id: str | None = Field(
        default=None,
        description="Associated parent task/attempt ID for trace correlation",
    )


class AgentPeerMessageResponse(BaseModel):
    """Result of peer consultation and canonical session archiving."""

    peer_message_id: str = Field(..., description="Unique peer communication trace ID")
    sender_agent_id: str = Field(..., description="Source agent identifier")
    target_agent_id: str = Field(..., description="Target agent identifier")
    query_content: str = Field(..., description="Initial query payload")
    reply_content: str = Field(..., description="Peer response payload")
    canonical_chat_id: str = Field(
        ...,
        description="Canonical Bot Chat session ID where dialogue is archived",
    )
    dispatched_at_epoch_ms: int = Field(..., description="Dispatch timestamp in milliseconds")
    latency_ms: float = Field(..., description="Peer turnaround latency in milliseconds")


class PeerSessionArchive(BaseModel):
    """Item in canonical peer message inbox archive."""

    canonical_chat_id: str = Field(..., description="Canonical chat ID")
    peer_agent_id: str = Field(..., description="Counterpart peer agent identifier")
    peer_agent_name: str = Field(..., description="Counterpart display name")
    last_message: str = Field(..., description="Snippet of latest message")
    message_count: int = Field(..., description="Total exchanged messages in this peer channel")
    updated_at_epoch_ms: int = Field(..., description="Last active epoch timestamp")
