"""Silence reassurance: a heartbeat message while a long agent run says nothing.

[INPUT]
- app.channels.core.bus::MessageBus (POS: sends the heartbeat and edits it in place)
- app.channels.routing.router_constants::_SILENCE_REASSURANCE_THRESHOLD, _MAX_REASSURANCE_COUNT (POS: default pacing)

[OUTPUT]
- run_reassurance_loop: background loop started next to the stream consumer and cancelled with it

[POS]
Edit-in-place heartbeat for long-task silence detection: the first heartbeat sends a message and later ones
edit it with the elapsed time and stage, so a quiet run never spams the chat. A failed edit falls back to a new
message; a channel that cannot edit gets the first heartbeat only. The caller owns the shared ``state`` and
refreshes ``last_activity`` on every event, and may pace the loop and name its message (the foreground turn uses
the defaults, a delegated run its own). Logger name consistent with the router stream.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING

from app.channels.i18n import get_text
from app.channels.routing.router_constants import (
    _MAX_REASSURANCE_COUNT,
    _SILENCE_REASSURANCE_THRESHOLD,
)
from app.channels.types import InboundMessage, MessagePriority, OutboundMessage

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus

logger = logging.getLogger("myrm.channels.routing.stream")


async def run_reassurance_loop(
    bus: MessageBus,
    msg: InboundMessage,
    chat_id: str,
    state: dict[str, float | int | str],
    *,
    interval: float | None = None,
    max_count: int | None = None,
    text_key: str = "reassurance_still_running",
    text_params: Mapping[str, str] | None = None,
) -> None:
    """Edit-in-place heartbeat during long silent periods.

    First heartbeat sends a new message and saves its ``message_id``.
    Subsequent heartbeats edit the same message with updated elapsed time
    and stage info, avoiding message spam. A failed edit falls back to a new
    message; a channel that does not support editing gets the first one only.

    ``interval`` (seconds of silence before a heartbeat) and ``max_count`` default to the foreground pacing;
    ``text_key`` names the catalog message and ``text_params`` fills its extra placeholders.
    """
    pace = _SILENCE_REASSURANCE_THRESHOLD if interval is None else interval
    limit = _MAX_REASSURANCE_COUNT if max_count is None else max_count
    heartbeat_mid: str | None = None
    loop_start = time.monotonic()

    channel_obj = bus.get_channel(msg.channel)
    can_edit = bool(channel_obj and channel_obj.capabilities.edit)

    sent_count = 0
    while sent_count < limit:
        await asyncio.sleep(pace)
        elapsed = time.monotonic() - float(state["last_activity"])
        if elapsed < pace:
            continue
        sent_count += 1
        steps = int(state["step_count"])
        stage = str(state["current_stage"])
        stage_suffix = f", {stage}" if stage else ""
        elapsed_mins = int((time.monotonic() - loop_start) // 60)
        text = get_text(
            msg,
            text_key,
            steps=steps,
            stage=stage_suffix,
            elapsed=elapsed_mins,
            **(text_params or {}),
        )

        try:
            if heartbeat_mid and can_edit:
                ok = await bus.edit_channel_message(
                    msg.channel,
                    chat_id,
                    heartbeat_mid,
                    text,
                )
                if not ok:
                    heartbeat_mid = None
            if not heartbeat_mid:
                reply = OutboundMessage(
                    channel=msg.channel,
                    recipient_id=chat_id,
                    content=text,
                    user_id=msg.user_id or "",
                    thread_id=msg.thread_id,
                    priority=MessagePriority.NORMAL,
                )
                heartbeat_mid = await bus.send_tracked(reply)
            logger.info(
                "reassurance_sent channel=%s chat=%s count=%d steps=%d elapsed_min=%d edit=%s",
                msg.channel,
                chat_id,
                sent_count,
                steps,
                elapsed_mins,
                heartbeat_mid is not None and can_edit,
            )
        except Exception:
            logger.warning(
                "reassurance_send_failed channel=%s chat=%s count=%d",
                msg.channel,
                chat_id,
                sent_count,
                exc_info=True,
            )
        state["last_activity"] = time.monotonic()
