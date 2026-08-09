"""Channel history cold-start backfill for preamble session setup.

[INPUT]
app.core.channel_bridge::get_channel_gateway (POS: 渠道网关单例)
app.services.chat.chat_service::ChatService (POS: 渠道会话持久化)

[OUTPUT]
maybe_backfill_channel_history(): 冷启动时从 IM 拉取近期消息写入 DB。

[POS]
execute_preamble 子模块：防止新 epoch 会话丢失渠道侧近期上下文。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.channels.types import InboundMessage

if TYPE_CHECKING:
    from .executor import ChannelAgentExecutor

logger = logging.getLogger(__name__)


async def maybe_backfill_channel_history(
    executor: "ChannelAgentExecutor",
    msg: InboundMessage,
    *,
    session_key: str,
    is_cold_start: bool,
    resolved_agent_id: str | None,
) -> None:
    if not is_cold_start:
        return

    if not hasattr(executor, "_backfill_locks"):
        executor._backfill_locks = set()

    if session_key in executor._backfill_locks:
        return

    executor._backfill_locks.add(session_key)
    try:
        from app.core.channel_bridge import get_channel_gateway
        from app.services.chat.chat_service import ChatService

        gateway = get_channel_gateway()
        if not gateway or not gateway.bus:
            return

        channel_inst = gateway.bus.channels.get(msg.channel)
        if not channel_inst or not hasattr(channel_inst, "fetch_history"):
            return

        backfill_limit = 15
        if msg.metadata and isinstance(msg.metadata.get("backfill_limit"), int):
            backfill_limit = msg.metadata["backfill_limit"]

        if backfill_limit <= 0:
            return

        hist_msgs = await channel_inst.fetch_history(msg.chat_id, limit=backfill_limit)
        if not hist_msgs:
            return

        chat = await ChatService.get_or_create_channel_chat(
            session_key,
            msg.channel,
            agent_id=resolved_agent_id,
        )
        base_time = msg.sent_at - (len(hist_msgs) * 0.001) - 1.0

        for i, h_msg in enumerate(hist_msgs):
            truncated_content = h_msg.content
            if truncated_content and len(truncated_content) > 500:
                truncated_content = truncated_content[:500] + "..."

            if not truncated_content and not h_msg.media:
                continue

            smoothed_time = datetime.fromtimestamp(base_time + (i * 0.001), tz=timezone.utc)

            await ChatService.append_message(
                chat.id,
                "user",
                truncated_content,
                smoothed_time,
                h_msg.sent_timezone or "UTC",
                message_id=h_msg.message_id,
            )
        logger.warning(
            "Channel history backfilled successfully for chat_id=%s, count=%d",
            chat.id,
            len(hist_msgs),
        )
    except Exception as ex:
        logger.warning(
            "Failed to perform channel history backfill for session %s: %s",
            session_key,
            ex,
        )
    finally:
        executor._backfill_locks.discard(session_key)
