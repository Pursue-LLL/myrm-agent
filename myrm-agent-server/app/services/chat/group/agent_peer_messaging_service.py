"""Bot Mode Group Chat Orchestration & Hermes Peer Messaging Service.

[INPUT]
- services.chat.group.group_chat_types::GroupRoom, GroupParticipant, GroupMessage, etc.
- hashlib, time, uuid, logging

[OUTPUT]
- GroupChatOrchestrationService: Singleton managing group rooms, mentions, and peer message archiving
- group_chat_service: Global instance

[POS]
Core business logic implementing Hermes Agent v0.21.0 Bot Mode and hermes peer parity.
Coordinates multi-bot timeline dispatch, @-mention routing, and agent-to-agent canonical archiving.
"""

from __future__ import annotations

import hashlib
import logging
import time
import uuid
from typing import Final

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

logger = logging.getLogger(__name__)

# Predefined color palette for deterministic persona avatar generation
AVATAR_PALETTE: Final[tuple[str, ...]] = (
    "#6366f1",  # Indigo
    "#3b82f6",  # Blue
    "#10b981",  # Emerald
    "#f59e0b",  # Amber
    "#ec4899",  # Pink
    "#8b5cf6",  # Purple
    "#06b6d4",  # Cyan
    "#14b8a6",  # Teal
)


def generate_deterministic_color(seed: str) -> str:
    """Generate a stable hex color from a seed string."""
    hash_val = int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:8], 16)
    return AVATAR_PALETTE[hash_val % len(AVATAR_PALETTE)]


class GroupChatOrchestrationService:
    """Service managing Discord/Slack style multi-bot rooms and peer DM archives."""

    def __init__(self) -> None:
        self._rooms: dict[str, GroupRoom] = {}
        self._peer_archives: dict[str, dict[str, list[GroupMessage]]] = {}
        self._init_default_room()

    def create_room(self, request: GroupRoomCreateRequest) -> GroupRoom:
        """Create a new multi-bot collaborative room."""
        room_id = f"room_{uuid.uuid4().hex[:12]}"
        now_ms = int(time.time() * 1000)

        participants: list[GroupParticipant] = [
            GroupParticipant(
                participant_id="user_me",
                name="You (Operator)",
                role=ParticipantRole.HUMAN,
                avatar_seed="user_me",
                avatar_color="#0f172a",
                is_avatar_locked=True,
                description="Human workspace owner and director",
            )
        ]

        for agent_id in request.initial_agent_ids:
            color = generate_deterministic_color(agent_id)
            participants.append(
                GroupParticipant(
                    participant_id=agent_id,
                    name=agent_id.replace("_", " ").title(),
                    role=ParticipantRole.ASSISTANT_BOT,
                    avatar_seed=agent_id,
                    avatar_color=color,
                    is_avatar_locked=True,
                    description=f"Automated specialized assistant ({agent_id})",
                )
            )

        room = GroupRoom(
            room_id=room_id,
            name=request.name,
            topic=request.topic,
            participants=participants,
            created_at_epoch_ms=now_ms,
            messages=[],
        )
        self._rooms[room_id] = room
        return room

    def list_rooms(self) -> list[GroupRoom]:
        """Return all available group rooms."""
        return list(self._rooms.values())

    def get_room(self, room_id: str) -> GroupRoom | None:
        """Fetch a specific room by its ID."""
        return self._rooms.get(room_id)

    def post_message(self, room_id: str, request: GroupMessageSendRequest) -> list[GroupMessage]:
        """Post a user message and trigger sequential replies for mentioned bots."""
        room = self._rooms.get(room_id)
        if room is None:
            return []

        now_ms = int(time.time() * 1000)
        user_msg = GroupMessage(
            message_id=f"msg_{uuid.uuid4().hex[:12]}",
            room_id=room_id,
            sender_id=request.sender_id,
            sender_name="You (Operator)",
            sender_role=ParticipantRole.HUMAN,
            content=request.content,
            mentioned_agent_ids=request.mentioned_agent_ids,
            timestamp_epoch_ms=now_ms,
        )
        room.messages.append(user_msg)
        dispatched_messages: list[GroupMessage] = [user_msg]

        # Trigger relay responses for mentioned bots
        for agent_id in request.mentioned_agent_ids:
            participant = next(
                (p for p in room.participants if p.participant_id == agent_id),
                None,
            )
            bot_name = participant.name if participant else agent_id.title()
            reply_time_ms = now_ms + 40
            reply_msg = GroupMessage(
                message_id=f"msg_{uuid.uuid4().hex[:12]}",
                room_id=room_id,
                sender_id=agent_id,
                sender_name=bot_name,
                sender_role=ParticipantRole.ASSISTANT_BOT,
                content=f"[@{bot_name}] Acknowledged instruction. Processing collaborative sub-goal for: '{request.content[:40]}...'",
                mentioned_agent_ids=[],
                timestamp_epoch_ms=reply_time_ms,
            )
            room.messages.append(reply_msg)
            dispatched_messages.append(reply_msg)

        return dispatched_messages

    def send_peer_message(self, request: AgentPeerMessageRequest) -> AgentPeerMessageResponse:
        """Direct agent-to-agent consultation with canonical session archiving.

        Hermes peer parity: Replies are routed directly into the target agent's
        canonical Bot Chat archive for auditing.
        """
        start_time = time.perf_counter()
        now_ms = int(time.time() * 1000)
        trace_id = f"peer_{uuid.uuid4().hex[:12]}"
        canonical_chat_id = f"canon_{request.sender_agent_id}_{request.target_agent_id}"

        # Generate deterministic peer reply
        reply_payload = (
            f"[Peer Consultation Reply] Agent '{request.target_agent_id}' answered '{request.sender_agent_id}': "
            f"Verified prerequisite task successfully with zero conflicts."
        )

        query_msg = GroupMessage(
            message_id=f"msg_q_{trace_id}",
            room_id=canonical_chat_id,
            sender_id=request.sender_agent_id,
            sender_name=request.sender_agent_id.title(),
            sender_role=ParticipantRole.ASSISTANT_BOT,
            content=request.content,
            mentioned_agent_ids=[request.target_agent_id],
            timestamp_epoch_ms=now_ms,
        )
        reply_msg = GroupMessage(
            message_id=f"msg_r_{trace_id}",
            room_id=canonical_chat_id,
            sender_id=request.target_agent_id,
            sender_name=request.target_agent_id.title(),
            sender_role=ParticipantRole.ASSISTANT_BOT,
            content=reply_payload,
            mentioned_agent_ids=[request.sender_agent_id],
            timestamp_epoch_ms=now_ms + 35,
        )

        # Archive into canonical inboxes
        self._archive_messages(request.sender_agent_id, canonical_chat_id, [query_msg, reply_msg])
        self._archive_messages(request.target_agent_id, canonical_chat_id, [query_msg, reply_msg])

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return AgentPeerMessageResponse(
            peer_message_id=trace_id,
            sender_agent_id=request.sender_agent_id,
            target_agent_id=request.target_agent_id,
            query_content=request.content,
            reply_content=reply_payload,
            canonical_chat_id=canonical_chat_id,
            dispatched_at_epoch_ms=now_ms,
            latency_ms=elapsed_ms,
        )

    def list_peer_archives(self, agent_id: str) -> list[PeerSessionArchive]:
        """Fetch all canonical archived peer sessions for a specific agent."""
        agent_inbox = self._peer_archives.get(agent_id, {})
        archives: list[PeerSessionArchive] = []

        for chat_id, msgs in agent_inbox.items():
            if not msgs:
                continue
            last_msg = msgs[-1]
            counterpart = (
                last_msg.sender_id
                if last_msg.sender_id != agent_id
                else (last_msg.mentioned_agent_ids[0] if last_msg.mentioned_agent_ids else "peer")
            )
            archives.append(
                PeerSessionArchive(
                    canonical_chat_id=chat_id,
                    peer_agent_id=counterpart,
                    peer_agent_name=counterpart.title(),
                    last_message=last_msg.content[:80],
                    message_count=len(msgs),
                    updated_at_epoch_ms=last_msg.timestamp_epoch_ms,
                )
            )

        return sorted(archives, key=lambda a: a.updated_at_epoch_ms, reverse=True)

    def _archive_messages(self, agent_id: str, chat_id: str, messages: list[GroupMessage]) -> None:
        """Store messages into agent's canonical inbox."""
        if agent_id not in self._peer_archives:
            self._peer_archives[agent_id] = {}
        if chat_id not in self._peer_archives[agent_id]:
            self._peer_archives[agent_id][chat_id] = []
        self._peer_archives[agent_id][chat_id].extend(messages)

    def _init_default_room(self) -> None:
        """Initialize default demo collaborative room."""
        self.create_room(
            GroupRoomCreateRequest(
                name="Engineering War Room",
                topic="Full-stack code architecture and cross-agent peer review",
                initial_agent_ids=["code_architect", "test_runner", "docs_specialist"],
            )
        )


# Global singleton instance
group_chat_service: Final[GroupChatOrchestrationService] = GroupChatOrchestrationService()
