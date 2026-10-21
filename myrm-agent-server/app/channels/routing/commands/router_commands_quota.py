"""Router quota mixin: /quota diagnostics and usage inspection.

[INPUT]
- channels.routing.router_host::RouterCommandsHost (POS: typing protocol for mixin host attributes.)
- channels.types::InboundMessage, OutboundMessage (POS: channel message types.)

[OUTPUT]
- RouterCommandsQuotaMixin: daily message quota status, visual ASCII progress, and reset countdown handler.

[POS]
Router quota mixin segment. Dedicated handler for /quota slash command with local SQLite lookup,
0 LLM token consumption, visual progress tracking, and relative reset countdown.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.channels.i18n import get_text
from app.channels.routing.router_host import RouterCommandsHost
from app.channels.types import InboundMessage, OutboundMessage

logger = logging.getLogger("app.channels.routing.router")


def render_ascii_progress(used: int, limit: int, width: int = 10) -> str:
    """Render a lightweight ASCII progress bar with percentage."""
    if limit <= 0:
        return ""
    safe_used = max(0, used)
    percent = min(100, int((safe_used / limit) * 100))
    filled = min(width, int(round((percent / 100) * width)))
    empty = width - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}] {percent}%"


def calculate_quota_countdown() -> tuple[int, int]:
    """Calculate remaining hours and minutes until next 00:00 UTC reset."""
    now = datetime.now(timezone.utc)
    next_reset = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    total_seconds = max(0, int((next_reset - now).total_seconds()))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    return hours, minutes


class RouterCommandsQuotaMixin:
    """Mixin: /quota inspection command for AgentRouter."""

    async def _handle_quota_command(self: RouterCommandsHost, msg: InboundMessage) -> None:
        """Handle /quota command: show user's daily quota and usage without invoking LLM."""
        chat_id = msg.chat_id or msg.sender_id
        pairing = getattr(self._resolver, "pairing", None)
        detail = await pairing.get_pairing_detail(msg.channel, msg.sender_id) if pairing else None

        role_str = detail[1].value if detail and detail[1] else "guest"
        daily_quota = detail[2] if detail and detail[2] is not None and detail[2] > 0 else None

        today_usage = 0
        try:
            from app.database.connection import get_session
            from app.database.repositories.channel_message_repo import (
                ChannelMessageRepository,
            )

            async with get_session() as session:
                today_usage = await ChannelMessageRepository.get_daily_trigger_count(session, msg.channel, msg.sender_id)
        except Exception:
            logger.exception("Failed to query daily usage for /quota: %s/%s", msg.channel, msg.sender_id)

        limit_str = str(daily_quota) if daily_quota is not None else get_text(msg, "quota_unlimited")
        remaining_str = str(max(0, daily_quota - today_usage)) if daily_quota is not None else get_text(msg, "quota_unlimited")
        progress_str = f" {render_ascii_progress(today_usage, daily_quota)}" if daily_quota is not None else ""

        hours, minutes = calculate_quota_countdown()
        try:
            reset_time_str = get_text(
                msg,
                "quota_reset_time",
                hours=str(hours),
                minutes=str(minutes),
            )
        except Exception:
            reset_time_str = get_text(msg, "quota_reset_time_static")

        lines: list[str] = [
            get_text(msg, "quota_header"),
            get_text(msg, "quota_user", user=msg.sender_id),
            get_text(msg, "quota_role", role=role_str),
            get_text(msg, "quota_usage", used=str(today_usage), limit=limit_str, progress=progress_str),
            get_text(msg, "quota_remaining", remaining=remaining_str),
            reset_time_str,
        ]

        reply = OutboundMessage(
            channel=msg.channel,
            recipient_id=chat_id,
            content="\n".join(lines),
            user_id=msg.user_id or "",
            thread_id=msg.thread_id,
            reply_to_id=((msg.message_id or str(msg.metadata.get("message_id", ""))) if msg.is_group else None),
        )
        await self._bus.publish_outbound(reply)
