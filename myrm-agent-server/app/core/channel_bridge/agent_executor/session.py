from __future__ import annotations

from app.channels.types import (
    InboundMessage,
    SessionKey,
    SessionPolicy,
    SessionResetMode,
    compute_daily_epoch,
)
from app.channels.types.thread_sharing import ThreadSharingMode


def _resolve_peer(msg: InboundMessage) -> tuple[str, str]:
    """Derive (peer_kind, peer_id) from an inbound message.

    Single source of truth for session key and channel budget key construction.
    Groups use chat_id; DMs use sender_id.
    """
    peer_kind = "group" if msg.is_group else "dm"
    peer_id = msg.chat_id if msg.is_group and msg.chat_id else msg.sender_id
    if not peer_id:
        peer_id = f"channel-{msg.channel}"
    return peer_kind, peer_id


def build_channel_budget_key(msg: InboundMessage) -> str:
    """Build the channel budget key prefix for budget guard lookup.

    Returns empty string for non-group messages (DM / WebUI).
    Format matches SessionKey.to_str() prefix: ``{channel}:{peer_kind}:{peer_id}``.
    Lowercased to match SessionKey.to_str() which applies .lower().
    """
    if not msg.is_group:
        return ""
    peer_kind, peer_id = _resolve_peer(msg)
    return f"{msg.channel}:{peer_kind}:{peer_id}".lower()


def _build_session_key(
    msg: InboundMessage,
    *,
    agent_id: str | None = None,
    thread_sharing_mode: ThreadSharingMode = ThreadSharingMode.ISOLATED,
) -> str:
    """Build a structured session key (base, without epoch).

    Dimensions: user + channel + peer_kind + peer + thread + agent.
    Groups use chat_id; DMs use sender_id.

    When thread_sharing_mode is SHARED, user identifier is removed from the key
    to enable all users in the same thread to share the conversation history.
    """
    peer_kind, peer_id = _resolve_peer(msg)

    sk = SessionKey(
        channel=msg.channel,
        peer_kind=peer_kind,
        peer_id=peer_id,
        thread_id=msg.thread_id,
        agent_id=agent_id,
    )
    return str(sk.to_str())


async def resolve_session_key(
    msg: InboundMessage,
    policy: SessionPolicy,
    *,
    agent_id: str | None = None,
    force_new_epoch: bool = False,
    thread_sharing_mode: ThreadSharingMode = ThreadSharingMode.ISOLATED,
) -> str:
    """Resolve the final session key according to the reset policy.

    - persistent: base key only (one Chat per peer forever)
    - daily: base key + date epoch (new Chat each day at reset_hour UTC)
    - idle: base key + time epoch (new Chat after idle_minutes of inactivity)
    - force_new_epoch: used by /new command to force a new Chat
    - thread_sharing_mode: ISOLATED (default) or SHARED (collaborative history)
    """
    from datetime import UTC, datetime

    base = _build_session_key(msg, agent_id=agent_id, thread_sharing_mode=thread_sharing_mode)

    if force_new_epoch:
        epoch = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%S")
        return f"{base}:e={epoch}"

    match policy.mode:
        case SessionResetMode.PERSISTENT:
            return base
        case SessionResetMode.DAILY:
            epoch = compute_daily_epoch(policy.daily_reset_hour)
            return f"{base}:e={epoch}"
        case SessionResetMode.IDLE:
            return await _resolve_idle_key(base, policy.idle_minutes)
    return base


async def _resolve_idle_key(
    base_key: str,
    idle_minutes: int,
) -> str:
    """Resolve session key for idle mode by checking the latest Chat's activity."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models import Chat

    async with get_session() as session:
        result = await session.execute(
            select(Chat.updated_at, Chat.channel_session_key)
            .where(
                Chat.channel_session_key.like(f"{base_key}%"),
            )
            .order_by(Chat.updated_at.desc())
            .limit(1)
        )
        row = result.first()

    now = datetime.now(tz=UTC)

    if row is None:
        return f"{base_key}:e={now.strftime('%Y%m%dT%H%M')}"

    updated_at: datetime = row[0]
    existing_key: str = row[1]

    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)

    elapsed = (now - updated_at).total_seconds()
    if elapsed > idle_minutes * 60:
        return f"{base_key}:e={now.strftime('%Y%m%dT%H%M')}"

    return existing_key
