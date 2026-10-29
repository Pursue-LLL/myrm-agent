"""Return a wake turn's reply to the IM chat its conversation lives in.

[INPUT]
- app.channels.core.gateway::ChannelGateway (POS: ``deliver_followup``, the router's delivery rules for a reply no message asked for)
- app.core.channel_bridge.wake_return.origins::WakeOrigins (POS: the message the chat was last talked in)
- app.services.agent.adaptive_wakeup.reply_return::WakeReplyReturner (POS: the port this implements)

[OUTPUT]
- ChannelWakeReplyReturner: carries a wake turn's reply to IM

[POS]
IM carrier of the wake-turn port, registered while the channel gateway runs. A chat the memory does not know (it
started in the app, or before the last restart) is left alone: its reply is in the chat for the web UI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.channels.core.gateway import ChannelGateway

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
        delivered = await self._gateway.deliver_followup(origin, reply)
        logger.info("Wake turn reply returned to %s: delivered=%s, session=%s", origin.channel, delivered, chat_id)
