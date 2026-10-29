"""Wake-turn return package: sends what a wake turn said back to the IM chat it belongs to.

[INPUT]
- wake_return.origins (POS: which message of an IM chat a reply goes back to)
- wake_return.returner (POS: the carrier registered with the wake-turn port)

[OUTPUT]
- ChannelWakeReplyReturner: the ``WakeReplyReturner`` implementation for IM channels
- WakeOrigins, get_wake_origins: the bounded memory of where each IM chat started

[POS]
Package entry for the IM half of a wake turn's reply.
"""

from __future__ import annotations

from .origins import WakeOrigins, get_wake_origins
from .returner import ChannelWakeReplyReturner

__all__ = ["ChannelWakeReplyReturner", "WakeOrigins", "get_wake_origins"]
