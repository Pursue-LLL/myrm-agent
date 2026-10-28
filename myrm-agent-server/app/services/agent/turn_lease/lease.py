"""Hold a chat session for a turn the server starts by itself.

[INPUT]
- app.services.agent.gateway::get_agent_gateway (POS: chat session reservation shared with user turns)
- myrm_agent_harness.utils.runtime.cancellation::CancellationRegistry, CancellationToken (POS: how the chat Stop button, a goal pause and the emergency stop find a turn)
- myrm_agent_harness.api.hooks::get_background_registry (POS: background jobs a turn started, per chat)

[OUTPUT]
- server_turn_lease: async context manager; yields the cancel token of a turn that holds its session

[POS]
A chat turn takes its session and registers a cancel token before its agent is built, so the Stop button, a pause
and the emergency stop can find it; a stopped chat turn also ends the background jobs it started. A turn the server
starts itself (goal continuation, an approval that timed out, a turn replayed after a restart, the wake turn after
background work settled) has no HTTP request to carry any of that, so it takes the same things here and gives them
back however it ends.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancellationToken

from app.services.agent.gateway import get_agent_gateway

logger = logging.getLogger(__name__)


@asynccontextmanager
async def server_turn_lease(session_id: str, turn_id: str) -> AsyncIterator[CancellationToken]:
    """Take ``session_id`` for the turn ``turn_id`` and yield the token its stream must run under.

    The token is registered under ``turn_id``, which is also the message id the session reports as active, so
    whoever stops the session finds it. On exit the token is unregistered, the background jobs of a cancelled turn
    are ended, and the reservation is given back unless the stream took it over (it then clears it itself) or a
    message that took the session meanwhile holds it.

    Raises:
        AgentBusyError: another turn holds the session.
        AgentDrainingError: the application is draining.
    """
    gateway = get_agent_gateway()
    gateway.reserve_session(session_id, active_message_id=turn_id)
    token = CancellationToken(request_id=turn_id)
    CancellationRegistry.register(token)
    try:
        yield token
    finally:
        CancellationRegistry.unregister(turn_id)
        try:
            if token.is_cancelled:
                await _stop_background_jobs(session_id)
        finally:
            if gateway.get_active_message_id(session_id) == turn_id:
                gateway.release_if_reserved_only(session_id)


async def _stop_background_jobs(session_id: str) -> None:
    """End what the stopped turn left running (``npm run dev &``), as the chat Stop button does."""
    from myrm_agent_harness.api.hooks import get_background_registry

    try:
        killed = await get_background_registry().kill_session_jobs(session_id)
    except Exception:
        logger.warning("Failed to end the background jobs of a stopped turn: session=%s", session_id, exc_info=True)
        return
    if killed:
        logger.info("Stopped turn ended %d background job(s): session=%s", killed, session_id)
