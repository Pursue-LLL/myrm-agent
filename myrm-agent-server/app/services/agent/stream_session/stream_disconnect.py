"""Disconnect tolerance for direct-SSE agent turns.

[INPUT]
- app.services.agent.stream_session.stream_session_types (POS: AgentStreamSession state and the grace-period constant)
- myrm_agent_harness.utils.runtime.cancellation::CancellationMonitor (POS: polls the checker and cancels the turn token)

[OUTPUT]
- build_disconnect_checker: predicate that turns a client absent past the grace period into True
- watch_client_disconnect: async context manager owning the monitor of one direct-SSE turn

[POS]
A direct-SSE client that stays away past ``GRACE_PERIOD_SECONDS`` cancels its turn.
Long-running turns are never cancelled for a disconnect: they finish in the
background and ``stream_pump`` notifies the user. Multiplexed turns are decoupled
from the HTTP request, so there is no connection to watch.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager

from myrm_agent_harness.utils.runtime.cancellation import CancellationMonitor

from app.services.agent.stream_session.stream_session_types import (
    GRACE_PERIOD_SECONDS,
    AgentStreamSession,
)

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SECONDS = 0.5


def build_disconnect_checker(session: AgentStreamSession) -> Callable[[], Coroutine[None, None, bool]]:
    """Build the predicate the turn's monitor polls: True once the client stayed away past the grace period."""

    async def _check() -> bool:
        disconnected = await session.http_request.is_disconnected()

        if not disconnected or session.collector.has_subscribers:
            session.disconnect_time = None
            return False

        if session.is_long_running_task:
            return False

        if session.disconnect_time is None:
            session.disconnect_time = time.time()
            logger.info(
                "PWA Disconnect Tolerance: Starting %ss grace period for message %s",
                GRACE_PERIOD_SECONDS,
                session.params.message_id,
            )
            return False

        elapsed = time.time() - session.disconnect_time
        if elapsed < GRACE_PERIOD_SECONDS:
            return False

        logger.warning(
            "PWA Disconnect Tolerance: Grace period expired (%ss), cancelling message %s",
            GRACE_PERIOD_SECONDS,
            session.params.message_id,
        )
        return True

    return _check


@asynccontextmanager
async def watch_client_disconnect(session: AgentStreamSession) -> AsyncIterator[None]:
    """Watch a direct-SSE turn's client for the duration of the ``async with`` body.

    The monitor is created, started and stopped inside this one scope, so a
    finished turn can never leave its polling task behind.
    """
    if session.request.multiplexed:
        yield
        return

    monitor = CancellationMonitor(
        token=session.cancel_token,
        disconnect_checker=build_disconnect_checker(session),
        check_interval=_CHECK_INTERVAL_SECONDS,
    )
    await monitor.start()
    try:
        yield
    finally:
        await monitor.stop()
