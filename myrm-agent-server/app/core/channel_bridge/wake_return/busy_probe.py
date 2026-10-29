"""Tell a wake turn that the member is mid-conversation in an IM chat.

[INPUT]
- app.channels.core.gateway::ChannelGateway (POS: says whether the router is running a turn for a conversation)
- wake_return.origins::WakeOrigins (POS: which message of an IM chat a reply goes back to)

[OUTPUT]
- ChannelChatBusyProbe: the ``ChatBusyProbe`` implementation for IM channels

[POS]
The IM half of "is the chat free". An IM turn runs under the router's session gate, which the agent gateway does not
see, so a wake turn would start beside it; the chat's origin names the gate key to ask.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .origins import WakeOrigins

if TYPE_CHECKING:
    from app.channels.core.gateway import ChannelGateway


class ChannelChatBusyProbe:
    """Whether the member of a remembered IM chat has a turn running in it."""

    def __init__(self, gateway: ChannelGateway, origins: WakeOrigins) -> None:
        self._gateway = gateway
        self._origins = origins

    def is_busy(self, chat_id: str) -> bool:
        """True while the router runs a turn for the conversation ``chat_id`` was last talked in; False for any other chat."""
        origin = self._origins.get(chat_id)
        return origin is not None and self._gateway.is_session_busy(origin)
