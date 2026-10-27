"""Bounded stop of an ACP agent that has stopped reading its stdin.

A prompt with images is one request of several MiB. An agent that stops reading leaves that write half done, and the
SDK sends ``session/cancel`` and its own shutdown through the same single sender, queued behind the write; the sender
swallows the cancellation of a wait on it, so no timeout around those calls can interrupt it. Ending the agent process
fails the write and frees everything queued behind it.

[INPUT]
- (stdlib only; the ACP SDK types are used for annotations)

[OUTPUT]
- STALLED_AGENT_TIMEOUT_SECONDS: how long cancel and transport exit wait before the agent process is ended
- cancel_session: send ``session/cancel`` within the bound, ending the agent process when it cannot be delivered
- leave_transport: leave the SDK transport within the bound, ending the agent process when it does not let go

[POS]
Stop path of AcpRuntime for an agent that is not reading. A healthy agent never reaches the bound: the notification
is written at once and the SDK's own graceful shutdown (close stdin, wait 2 s, terminate, wait 2 s, kill) ends inside it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio.subprocess import Process

    from acp import ClientSideConnection

logger = logging.getLogger(__name__)

STALLED_AGENT_TIMEOUT_SECONDS = 5.0


def kill_process(process: Process | None) -> None:
    """End the agent process; the write it never read then fails, which frees everything queued behind it."""
    if process is not None and process.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            process.kill()


async def cancel_session(conn: ClientSideConnection, session_id: str, process: Process | None, name: str) -> None:
    """Send ``session/cancel``; when it waits behind a prompt the agent is not reading, end the process instead."""
    try:
        async with asyncio.timeout(STALLED_AGENT_TIMEOUT_SECONDS):
            await conn.cancel(session_id=session_id)
    except TimeoutError:
        logger.warning("acp_cancel_timeout name=%s timeout_s=%.0f", name, STALLED_AGENT_TIMEOUT_SECONDS)
        kill_process(process)


async def leave_transport(
    ctx: AbstractAsyncContextManager[tuple[ClientSideConnection, Process]],
    process: Process | None,
    name: str,
) -> None:
    """Leave the SDK transport, ending the agent process when it does not let go within the bound."""
    leaving = asyncio.ensure_future(ctx.__aexit__(None, None, None))
    try:
        await asyncio.wait({leaving}, timeout=STALLED_AGENT_TIMEOUT_SECONDS)
        if not leaving.done():
            logger.warning("acp_transport_exit_timeout name=%s timeout_s=%.0f", name, STALLED_AGENT_TIMEOUT_SECONDS)
            kill_process(process)
            await asyncio.wait({leaving}, timeout=STALLED_AGENT_TIMEOUT_SECONDS)
    finally:
        if not leaving.done():
            leaving.cancel()
    if leaving.done() and not leaving.cancelled():
        leaving.result()
