"""Queue the one wake turn that answers settled background work and start it once its chat is free.

[INPUT]
- app.services.agent.gateway::get_agent_gateway, AgentGateway, AgentDrainingError (POS: whether a turn holds the chat)
- app.services.agent.adaptive_wakeup.chat_busy::is_chat_busy (POS: whether an IM turn, which the gateway cannot see, holds the chat)
- app.services.agent.turn_lease::server_turn_lease (POS: the wake turn takes the chat and a cancel token like any server-started turn)
- myrm_agent_harness.utils.runtime.cancellation::CancellationToken (POS: how a Stop, a goal pause and the emergency stop reach the turn)

[OUTPUT]
- WakeTurnRunner: what the scheduler starts once it holds the chat
- schedule_wake_turn: queue the wake turn of a chat; settlements that land while one is queued share it

[POS]
A settled background task must not start a second turn beside one the user is running, nor one the user cannot stop.
The scheduler waits until the chat is free, holds it under the turn lease while the runner works, and leaves every
decision about whether the turn should happen to the runner.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.services.agent.adaptive_wakeup.chat_busy import is_chat_busy
from app.services.agent.gateway import AgentDrainingError, AgentGateway, get_agent_gateway
from app.services.agent.turn_lease import server_turn_lease

logger = logging.getLogger(__name__)

# (chat id, turn id, the lease's cancel token, when the latest settlement the turn answers landed)
WakeTurnRunner = Callable[[str, str, CancellationToken, datetime], Awaitable[None]]

_POLL_INTERVAL_SECONDS = 1.0
# A goal turn may run as long as the gateway allows; a wake that waited longer is dropped and its notice row waits for
# the next message instead.
_MAX_WAIT_SECONDS = AgentGateway.GOAL_ACTIVE_TIMEOUT_SECONDS


@dataclass
class _QueuedWake:
    """A wake turn that has not taken its chat yet; ``settled_at`` is the latest settlement it will answer."""

    settled_at: datetime


# The queued wake of each chat. A wake leaves the queue when it takes the chat, so a settlement that lands while it
# runs queues the next one instead of being lost.
_waiting: dict[str, _QueuedWake] = {}
_tasks: set[asyncio.Task[None]] = set()


def schedule_wake_turn(chat_id: str, run: WakeTurnRunner) -> None:
    """Queue the wake turn of ``chat_id``; a settlement that lands while one is queued joins it."""
    now = datetime.now(tz=UTC)
    if (queued := _waiting.get(chat_id)) is not None:
        queued.settled_at = now
        logger.info("Wake turn already queued, settlement joins it: session=%s", chat_id)
        return
    queued = _waiting[chat_id] = _QueuedWake(settled_at=now)
    task = asyncio.create_task(_wake_when_free(chat_id, run, queued), name=f"wake-turn:{chat_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def _leave_queue(chat_id: str, queued: _QueuedWake) -> None:
    # The entry may already belong to the wake queued behind this one.
    if _waiting.get(chat_id) is queued:
        del _waiting[chat_id]


async def _wake_when_free(chat_id: str, run: WakeTurnRunner, queued: _QueuedWake) -> None:
    try:
        if not await _wait_until_free(chat_id):
            logger.warning("Wake turn dropped, the chat stayed busy for %.0fs: session=%s", _MAX_WAIT_SECONDS, chat_id)
            return
        turn_id = str(uuid.uuid4())
        # Nothing yields between seeing the chat free and taking it, so no message can slip in between.
        async with server_turn_lease(chat_id, turn_id) as cancel_token:
            _leave_queue(chat_id, queued)
            await run(chat_id, turn_id, cancel_token, queued.settled_at)
    except AgentDrainingError:
        logger.info("Wake turn not started, the application is draining: session=%s", chat_id)
    except Exception:
        logger.error("Wake turn failed: session=%s", chat_id, exc_info=True)
    finally:
        _leave_queue(chat_id, queued)


async def _wait_until_free(chat_id: str) -> bool:
    """Wait until no turn holds the chat; False when it stayed busy for ``_MAX_WAIT_SECONDS``.

    A turn holds the chat when the agent gateway says so (the app's own turns, goal turns, other wake turns) or when
    the channel router runs one for it (a member talking in an IM chat).
    """
    gateway = get_agent_gateway()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _MAX_WAIT_SECONDS
    while gateway.is_session_active(chat_id) or is_chat_busy(chat_id):
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    return True
