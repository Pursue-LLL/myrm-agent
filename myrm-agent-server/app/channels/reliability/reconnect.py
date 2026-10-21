"""Reconnect loop with exponential backoff + jitter for long-lived connections.

Provides a reusable pattern for WebSocket/polling channels that need
auto-reconnect on failure. Eliminates duplicated backoff logic across
7+ channel providers.

[INPUT]
- app.channels.types::ChannelStatus (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- reconnect_loop: Run *connect_fn* in a loop, reconnecting with exponential...

[POS]
Reconnect loop with exponential backoff + jitter for long-lived connections.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable, Coroutine

from app.channels.types import ChannelStatus

logger = logging.getLogger(__name__)

StatusGetter = Callable[[], ChannelStatus]
ConnectFn = Callable[[], Coroutine[object, object, None]]


async def reconnect_loop(
    connect_fn: ConnectFn,
    status_getter: StatusGetter,
    *,
    channel_name: str = "",
    initial_backoff: float = 1.0,
    max_backoff: float = 60.0,
    jitter: float = 0.5,
) -> None:
    """Run *connect_fn* in a loop, reconnecting with exponential backoff on failure.

    Stops when ``status_getter()`` returns anything other than ``RUNNING``.
    ``connect_fn`` should run until the connection drops (e.g. WebSocket closed,
    poll endpoint down), then raise an exception to trigger reconnect.

    Args:
        connect_fn: Async function that establishes and maintains the connection.
        status_getter: Returns current channel status; loop exits if not RUNNING.
        channel_name: Used in log messages.
        initial_backoff: Starting delay in seconds after first failure.
        max_backoff: Maximum delay between reconnect attempts.
        jitter: Random jitter factor (0.0–1.0) to prevent thundering herd.
    """
    backoff = initial_backoff

    while status_getter() == ChannelStatus.RUNNING:
        try:
            await connect_fn()
            backoff = initial_backoff
        except asyncio.CancelledError:
            break
        except Exception as exc:
            jittered = backoff * (1.0 + random.uniform(-jitter, jitter))
            jittered = max(0.1, jittered)
            logger.warning(
                "%s: connection error, reconnecting in %.1fs: %s",
                channel_name or "Channel",
                jittered,
                exc,
            )
            await asyncio.sleep(jittered)
            backoff = min(backoff * 2, max_backoff)
