"""Bounded stop of one channel, shared by every place the gateway stops a channel.

``channel.stop()`` may talk to the platform (clear drafts, delete commands, log out), and on a network that drops
packets each of those calls waits out the client timeout. The gateway stops channels while holding up something
else (the health loop, a credential save, the shutdown), so the wait is capped and a stop that does not finish is
abandoned with a warning instead of blocking the caller. An abandoned stop ends where it is, so a provider's
``stop()`` releases its own task or connection first and leaves the network cleanup for last (``BaseChannel.stop``).

[INPUT]
- channels.core.base::BaseChannel (POS: channel abstract base class)

[OUTPUT]
- stop_channel: ``await channel.stop()`` for at most ``_STOP_TIMEOUT`` seconds; a timeout or an error is logged as a
  warning and never raised, a cancellation of the caller still propagates
- _STOP_TIMEOUT: the cap, well above a normal stop and below the health check interval

[POS]
Stop primitive of the channel gateway. The health restart, ``disable_channel``, ``remove_channel``, ``reload_channel``
and the gateway shutdown all stop channels through it.
"""

from __future__ import annotations

import asyncio
import logging

from app.channels.core.base import BaseChannel

logger = logging.getLogger(__name__)

_STOP_TIMEOUT = 10.0


async def stop_channel(name: str, channel: BaseChannel) -> None:
    """Stop *channel* (registered as *name*), waiting at most ``_STOP_TIMEOUT`` seconds."""
    try:
        async with asyncio.timeout(_STOP_TIMEOUT) as deadline:
            await channel.stop()
    except Exception:
        if deadline.expired():
            logger.warning("Channel '%s' did not stop within %.0fs; continuing without waiting for it", name, _STOP_TIMEOUT)
        else:
            logger.warning("Channel '%s': error while stopping", name, exc_info=True)
