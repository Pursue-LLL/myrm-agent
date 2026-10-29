"""Plug the IM half of a wake turn into the ports of the wake turn while the channel gateway runs.

[INPUT]
- app.channels.core.gateway::ChannelGateway (POS: what the carrier and the probe ask about an IM chat)
- wake_return.origins::get_wake_origins (POS: the one memory of where each IM chat started, shared by both)
- wake_return.returner::ChannelWakeReplyReturner, wake_return.busy_probe::ChannelChatBusyProbe (POS: the two implementations)
- app.services.agent.adaptive_wakeup.reply_return::set_wake_reply_returner (POS: the port a wake turn's reply leaves through)
- app.services.agent.adaptive_wakeup.chat_busy::set_chat_busy_probe (POS: the port a wake turn asks before it takes a chat)

[OUTPUT]
- register_wake_im_ports: from now on a wake turn waits for the member's turn in an IM chat and replies in that chat
- clear_wake_im_ports: the wake turn goes back to knowing only the app

[POS]
Called by the channel bridge's start and stop: with no gateway running there is no router to ask and no channel to
reply in, so the ports must not outlive it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent.adaptive_wakeup.chat_busy import set_chat_busy_probe
from app.services.agent.adaptive_wakeup.reply_return import set_wake_reply_returner

from .busy_probe import ChannelChatBusyProbe
from .origins import get_wake_origins
from .returner import ChannelWakeReplyReturner

if TYPE_CHECKING:
    from app.channels.core.gateway import ChannelGateway


def register_wake_im_ports(gateway: ChannelGateway) -> None:
    """Register the reply carrier and the busy probe of ``gateway``; both read the same IM chat memory."""
    origins = get_wake_origins()
    set_wake_reply_returner(ChannelWakeReplyReturner(gateway, origins))
    set_chat_busy_probe(ChannelChatBusyProbe(gateway, origins))


def clear_wake_im_ports() -> None:
    """Remove the carrier and the probe."""
    set_wake_reply_returner(None)
    set_chat_busy_probe(None)
