"""Bounded stop of an ACP agent that has stopped reading its stdin.

A prompt with images is one request of several MiB. An agent that stops reading leaves that write half done, and the
SDK sends ``session/cancel`` and its own shutdown through the same single sender, queued behind the write; the sender
swallows the cancellation of a wait on it, so no timeout around those calls can interrupt it. Ending the agent and
everything it started fails the write, because nothing holds the read end of the agent's stdin any more, and frees
everything queued behind it.

[INPUT]
- toolkits.code_execution.session.process_tree::kill_process_tree (POS: ends a process and its whole tree, escalating from terminate to kill)
- utils.os_compat::IS_WIN (POS: platform switch of the tree kill)

[OUTPUT]
- STALLED_AGENT_TIMEOUT_SECONDS: how long cancel and transport exit wait before the agent and its tools are ended
- end_agent: end the agent process and every process it started
- cancel_session: send ``session/cancel`` within the bound, ending the agent when it cannot be delivered
- leave_transport: leave the SDK transport within the bound, ending the agent when it does not let go

[POS]
Stop path of AcpRuntime for an agent that is not reading. A healthy agent never reaches the bound: the notification
is written at once and the SDK's own graceful shutdown (close stdin, wait 2 s, terminate, wait 2 s, kill) ends inside it.
The SDK spawns the agent in the host's own process group, which must never be signalled, so the tools it started are
ended one by one through the process tree. Ending the agent alone would leave them running, and a tool that inherited the
agent's stdin would keep the stuck write from ever failing.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from myrm_agent_harness.utils.os_compat import IS_WIN

if TYPE_CHECKING:
    from asyncio.subprocess import Process

    from acp import ClientSideConnection

logger = logging.getLogger(__name__)

STALLED_AGENT_TIMEOUT_SECONDS = 5.0
# Between the polite signal and the kill. The bound above has already been waited, so a hung agent gets no more.
_TREE_GRACE_SECONDS = 0.5


async def end_agent(process: Process | None) -> None:
    """End the agent and every process it started; the write it never read then fails and frees the queue."""
    # A reaped agent's PID may already belong to an unrelated process.
    if process is None or process.returncode is not None:
        return
    # Imported here: the session package loads the whole shell stack, which only this stop path needs.
    from myrm_agent_harness.toolkits.code_execution.session.process_tree import kill_process_tree

    # Shielded like the shell's own stop: a caller cancelled in the middle must not leave the tools half ended.
    await asyncio.shield(kill_process_tree(process, IS_WIN, _TREE_GRACE_SECONDS))


async def cancel_session(conn: ClientSideConnection, session_id: str, process: Process | None, name: str) -> None:
    """Send ``session/cancel``; when it waits behind a prompt the agent is not reading, end the agent instead."""
    try:
        async with asyncio.timeout(STALLED_AGENT_TIMEOUT_SECONDS):
            await conn.cancel(session_id=session_id)
    except TimeoutError:
        logger.warning("acp_cancel_timeout name=%s timeout_s=%.0f", name, STALLED_AGENT_TIMEOUT_SECONDS)
        await end_agent(process)


async def leave_transport(
    ctx: AbstractAsyncContextManager[tuple[ClientSideConnection, Process]],
    process: Process | None,
    name: str,
) -> None:
    """Leave the SDK transport, ending the agent when it does not let go within the bound."""
    leaving = asyncio.ensure_future(ctx.__aexit__(None, None, None))
    try:
        await asyncio.wait({leaving}, timeout=STALLED_AGENT_TIMEOUT_SECONDS)
        if not leaving.done():
            logger.warning("acp_transport_exit_timeout name=%s timeout_s=%.0f", name, STALLED_AGENT_TIMEOUT_SECONDS)
            await end_agent(process)
            await asyncio.wait({leaving}, timeout=STALLED_AGENT_TIMEOUT_SECONDS)
    finally:
        if not leaving.done():
            leaving.cancel()
    if leaving.done() and not leaving.cancelled():
        leaving.result()
