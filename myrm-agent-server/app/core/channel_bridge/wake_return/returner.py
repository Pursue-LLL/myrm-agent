"""Return a wake turn's reply to the IM chat its conversation lives in.

[INPUT]
- myrm_agent_harness.utils.text_utils::strip_internal_markers (POS: removes the security boundary markers a model may echo; every IM reply goes through it)
- app.channels.core.gateway::ChannelGateway (POS: ``deliver_followup``, the router's delivery rules for a reply no message asked for)
- app.channels.i18n::get_text, resolve_message_locale (POS: the language of the notes, and the one-line reply of a message that is only attachments)
- app.core.channel_bridge.agent_executor.deliverable::append_deliverable_notes, collect_deliverable_paths_from_text, resolve_chat_workspace_root (POS: attaches the workspace files a reply text names)
- app.core.channel_bridge.wake_return.origins::WakeOrigins (POS: the message the chat was last talked in)
- app.services.agent.adaptive_wakeup.reply_return::WakeReplyReturner (POS: the port this implements)

[OUTPUT]
- ChannelWakeReplyReturner: carries a wake turn's reply to IM

[POS]
IM carrier of the wake-turn port, registered while the channel gateway runs. A chat the memory does not know (it
started in the app, or before the last restart) is left alone: its reply is in the chat for the web UI. The reply is
cleaned the way the answer to an IM message is before it leaves the app: boundary markers removed, and the workspace
files it names attached.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.channels.i18n import get_text, resolve_message_locale

if TYPE_CHECKING:
    from app.channels.core.gateway import ChannelGateway
    from app.channels.types import InboundMessage, MediaAttachment

    from .origins import WakeOrigins

logger = logging.getLogger(__name__)


class ChannelWakeReplyReturner:
    """Hands the reply of a wake turn to the router, to be delivered like the answer to the chat's last message."""

    def __init__(self, gateway: ChannelGateway, origins: WakeOrigins) -> None:
        self._gateway = gateway
        self._origins = origins

    async def return_reply(self, chat_id: str, reply: str) -> None:
        origin = self._origins.get(chat_id)
        if origin is None:
            return
        # The model may echo the boundary markers that wrap untrusted data; an IM reader must not see them.
        reply = strip_internal_markers(reply).strip()
        if not reply:
            return
        content, media = await _with_deliverables(chat_id, reply, origin)
        delivered = await self._gateway.deliver_followup(origin, content, media)
        logger.info("Wake turn reply returned to %s: delivered=%s, session=%s", origin.channel, delivered, chat_id)


async def _with_deliverables(chat_id: str, reply: str, origin: InboundMessage) -> tuple[str, tuple[MediaAttachment, ...]]:
    """``reply`` with the workspace files it names attached, as the answer to an IM message has them.

    A scan that fails leaves the reply as plain text: the files are still in the workspace.
    """
    # The executor package imports this one (the turn registers its chat here), so the scan is imported when needed.
    from app.core.channel_bridge.agent_executor.deliverable import (
        append_deliverable_notes,
        collect_deliverable_paths_from_text,
        resolve_chat_workspace_root,
    )

    workspace_root = await resolve_chat_workspace_root(chat_id)
    if not workspace_root:
        return reply, ()
    try:
        text, media, oversized_notes, compressed_notes = await asyncio.to_thread(
            collect_deliverable_paths_from_text, reply, workspace_root=workspace_root
        )
    except Exception:
        logger.warning(
            "Wake turn reply: scanning for deliverable files failed, sending text only: session=%s", chat_id, exc_info=True
        )
        return reply, ()
    locale = resolve_message_locale(origin)
    text = append_deliverable_notes(text, locale=locale, oversized_notes=oversized_notes, compressed_notes=compressed_notes)
    if media and not text.strip():
        text = get_text(origin, "deliverable_attached_only")
    return text, tuple(media)
