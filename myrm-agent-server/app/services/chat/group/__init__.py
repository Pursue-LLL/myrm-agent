"""Bot Mode Multi-Agent Group Chat and Peer Messaging Package.

[INPUT]
- app.services.chat.group.group_chat_types
- app.services.chat.group.agent_peer_messaging_service

[OUTPUT]
- Public facades for group chat rooms, mention orchestration, and Hermes peer parity

[POS]
app/services/chat/group/__init__.py
Package entrypoint exposing group chat domain models and orchestration services.
"""

from __future__ import annotations

from app.services.chat.group.agent_peer_messaging_service import (
    AVATAR_PALETTE,
    GroupChatOrchestrationService,
    generate_deterministic_color,
    group_chat_service,
)
from app.services.chat.group.group_chat_types import (
    AgentPeerMessageRequest,
    AgentPeerMessageResponse,
    GroupMessage,
    GroupMessageSendRequest,
    GroupParticipant,
    GroupRoom,
    GroupRoomCreateRequest,
    ParticipantRole,
    PeerSessionArchive,
)

__all__ = [
    "AVATAR_PALETTE",
    "AgentPeerMessageRequest",
    "AgentPeerMessageResponse",
    "GroupChatOrchestrationService",
    "GroupMessage",
    "GroupMessageSendRequest",
    "GroupParticipant",
    "GroupRoom",
    "GroupRoomCreateRequest",
    "ParticipantRole",
    "PeerSessionArchive",
    "generate_deterministic_color",
    "group_chat_service",
]
