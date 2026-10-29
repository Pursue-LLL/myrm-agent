"""Wake-turn IM package: the wake turn waits for the member in an IM chat and sends its reply back there.

[INPUT]
- wake_return.origins (POS: which message of an IM chat a reply goes back to)
- wake_return.returner (POS: the carrier registered with the wake-turn reply port)
- wake_return.busy_probe (POS: the probe registered with the wake-turn busy port)
- wake_return.wiring (POS: registers and clears both for as long as the channel gateway runs)

[OUTPUT]
- ChannelWakeReplyReturner: the ``WakeReplyReturner`` implementation for IM channels
- ChannelChatBusyProbe: the ``ChatBusyProbe`` implementation for IM channels
- WakeOrigins, get_wake_origins: the bounded memory of where each IM chat started
- register_wake_im_ports, clear_wake_im_ports: plug the carrier and the probe into the wake-turn ports, and take them out

[POS]
Package entry for the IM half of a wake turn: whether the member is mid-conversation, and where its reply goes.
"""

from __future__ import annotations

from .busy_probe import ChannelChatBusyProbe
from .origins import WakeOrigins, get_wake_origins
from .returner import ChannelWakeReplyReturner
from .wiring import clear_wake_im_ports, register_wake_im_ports

__all__ = [
    "ChannelChatBusyProbe",
    "ChannelWakeReplyReturner",
    "WakeOrigins",
    "clear_wake_im_ports",
    "get_wake_origins",
    "register_wake_im_ports",
]
