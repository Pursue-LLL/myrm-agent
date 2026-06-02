"""Cross-platform session handoff service.

[INPUT]
- database.models.chat::Chat (POS: session record with channel_session_key)
- database.models.channel::ChannelPairingModel (POS: external identity mapping)
- channels.types.session::SessionKey, SessionPolicy, SessionResetMode, compute_daily_epoch

[OUTPUT]
- HandoffResult: result dataclass
- handoff_chat: transfer a Chat session to a different channel

[POS]
Rebinds a Chat's channel_session_key to point at a target channel,
so subsequent messages on that channel resume the same conversation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.channels.types.session import (
    SessionKey,
    SessionPolicy,
    SessionResetMode,
    compute_daily_epoch,
)
from app.database.connection import get_session
from app.database.models.channel import ChannelPairingModel
from app.database.models.chat import Chat

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HandoffResult:
    success: bool
    error: str = ""
    target_channel: str = ""
    target_session_key: str = ""


def _build_target_session_key(
    target_channel: str,
    peer_id: str,
    policy: SessionPolicy,
    agent_id: str | None = None,
) -> str:
    """Build a session key that matches what resolve_session_key would produce."""
    sk = SessionKey(
        channel=target_channel,
        peer_kind="dm",
        peer_id=peer_id,
        agent_id=agent_id,
    )
    base = sk.to_str()
    match policy.mode:
        case SessionResetMode.PERSISTENT:
            return base
        case SessionResetMode.DAILY:
            epoch = compute_daily_epoch(policy.daily_reset_hour)
            return f"{base}:e={epoch}"
        case SessionResetMode.IDLE:
            epoch = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M")
            return f"{base}:e={epoch}"
    return base


async def handoff_chat(
    chat_id: str,
    target_channel_name: str,
    *,
    policy: SessionPolicy | None = None,
) -> HandoffResult:
    """Transfer a chat session to a target channel.

    Validates preconditions (chat exists, target channel connected, user paired),
    resolves UNIQUE constraint conflicts, and rebinds the Chat record.
    """
    from app.core.channel_bridge import channel_gateway

    if policy is None:
        policy = SessionPolicy()

    async with get_session() as session:
        chat = (
            await session.execute(select(Chat).where(Chat.id == chat_id))
        ).scalar_one_or_none()
        if not chat:
            return HandoffResult(success=False, error=f"Chat {chat_id} not found")

        target_ch = channel_gateway.bus.get_channel(target_channel_name)
        if not target_ch:
            return HandoffResult(
                success=False,
                error=f"Channel '{target_channel_name}' not found",
                target_channel=target_channel_name,
            )
        if not target_ch.is_connected:
            return HandoffResult(
                success=False,
                error=f"Channel '{target_channel_name}' is not connected",
                target_channel=target_channel_name,
            )

        if chat.source == target_channel_name and chat.channel_session_key:
            sk = SessionKey.parse(chat.channel_session_key)
            if sk and sk.channel == target_channel_name:
                return HandoffResult(
                    success=False,
                    error="Already on this channel",
                    target_channel=target_channel_name,
                )

        pairing = (
            await session.execute(
                select(ChannelPairingModel)
                .where(
                    ChannelPairingModel.channel == target_channel_name,
                    ChannelPairingModel.status == "active",
                )
                .order_by(ChannelPairingModel.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        if not pairing:
            return HandoffResult(
                success=False,
                error=f"No pairing for channel '{target_channel_name}'",
                target_channel=target_channel_name,
            )

        target_key = _build_target_session_key(
            target_channel_name,
            pairing.sender_id,
            policy,
            agent_id=chat.agent_id,
        )

        # Unbind any Chat currently holding target_key to avoid UNIQUE conflict
        existing = (
            await session.execute(
                select(Chat).where(
                    Chat.channel_session_key == target_key,
                    Chat.id != chat_id,
                )
            )
        ).scalar_one_or_none()

        if existing:
            logger.info(
                "Handoff: unbinding Chat %s from key %s (replaced by %s)",
                existing.id,
                target_key,
                chat_id,
            )
            existing.channel_session_key = None
            await session.flush()

        chat.channel_session_key = target_key
        chat.source = target_channel_name

        await session.commit()

    logger.info(
        "Handoff: chat %s -> channel %s (key=%s)",
        chat_id,
        target_channel_name,
        target_key,
    )
    return HandoffResult(
        success=True,
        target_channel=target_channel_name,
        target_session_key=target_key,
    )
