"""Run the one wake turn that answers settled background work, once the chat is free.

[INPUT]
- app.services.agent.gateway::get_agent_gateway, AgentGateway, AgentDrainingError (POS: whether a turn holds the chat)
- app.services.agent.turn_lease::server_turn_lease (POS: the wake turn takes the chat and a cancel token like any server-started turn)
- app.services.agent.wakeup_handler::ServerWakeupHandler (POS: builds the agent and streams the wake turn)
- app.services.agent.adaptive_wakeup.service::get_adaptive_wakeup_service (POS: the user's stop flag and last human turn)
- myrm_agent_harness.agent.security.guards.estop::check_estop (POS: global emergency stop)

[OUTPUT]
- schedule_wake_turn: queue the wake turn of a chat; settlements that land while one is queued share it

[POS]
A settled background task must not start a second turn beside one the user is running, nor one the user cannot stop.
The wake therefore waits until the chat is free, holds it under the turn lease while it runs, and gives way when the
user stopped the session, wrote since the notice, or the emergency stop is on.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.agent.security.guards.estop import check_estop
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken

from app.services.agent.gateway import AgentDrainingError, AgentGateway, get_agent_gateway
from app.services.agent.turn_lease import server_turn_lease

logger = logging.getLogger(__name__)

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


def schedule_wake_turn(chat_id: str, agent_id: str) -> bool:
    """Queue the wake turn of ``chat_id``; False when one is already queued and answers this settlement too."""
    now = datetime.now(tz=UTC)
    if (queued := _waiting.get(chat_id)) is not None:
        queued.settled_at = now
        logger.info("Wake turn already queued, settlement joins it: session=%s", chat_id)
        return False
    queued = _waiting[chat_id] = _QueuedWake(settled_at=now)
    task = asyncio.create_task(_wake_when_free(chat_id, agent_id, queued), name=f"wake-turn:{chat_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


def _leave_queue(chat_id: str, queued: _QueuedWake) -> None:
    # The entry may already belong to the wake queued behind this one.
    if _waiting.get(chat_id) is queued:
        del _waiting[chat_id]


async def _wake_when_free(chat_id: str, agent_id: str, queued: _QueuedWake) -> None:
    try:
        if not await _wait_until_free(chat_id):
            logger.warning("Wake turn dropped, the chat stayed busy for %.0fs: session=%s", _MAX_WAIT_SECONDS, chat_id)
            return
        turn_id = str(uuid.uuid4())
        # Nothing yields between seeing the chat free and taking it, so no message can slip in between.
        async with server_turn_lease(chat_id, turn_id) as cancel_token:
            _leave_queue(chat_id, queued)
            await _run_leased(chat_id, agent_id, turn_id, cancel_token, queued.settled_at)
    except AgentDrainingError:
        logger.info("Wake turn not started, the application is draining: session=%s", chat_id)
    except Exception:
        logger.error("Wake turn failed: session=%s", chat_id, exc_info=True)
    finally:
        _leave_queue(chat_id, queued)


async def _wait_until_free(chat_id: str) -> bool:
    """Wait until no turn holds the chat; False when it stayed busy for ``_MAX_WAIT_SECONDS``."""
    gateway = get_agent_gateway()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _MAX_WAIT_SECONDS
    while gateway.is_session_active(chat_id):
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    return True


async def _run_leased(chat_id: str, agent_id: str, turn_id: str, cancel_token: CancellationToken, settled_at: datetime) -> None:
    if reason := await _skip_reason(chat_id, settled_at):
        logger.info("Wake turn skipped, %s: session=%s", reason, chat_id)
        return

    from app.services.agent.wakeup_handler import ServerWakeupHandler

    await ServerWakeupHandler().stream_wake_turn(chat_id, agent_id, turn_id, cancel_token)


async def _skip_reason(chat_id: str, settled_at: datetime) -> str | None:
    """Why the wake turn must not run, or None when it should."""
    if check_estop() is not None:
        return "the emergency stop is on"

    from app.services.agent.adaptive_wakeup.service import get_adaptive_wakeup_service

    budget = get_adaptive_wakeup_service().get_budget_state(chat_id)
    if budget.is_user_stopped:
        return "the user stopped the session"
    if budget.last_human_reset_time is not None and budget.last_human_reset_time > settled_at:
        # The user's own turn started after the last notice, so the model has read them all.
        return "the user wrote after the notice"

    from app.services.budget.enforcer import should_block_execution

    if await should_block_execution():
        return "the daily budget is exceeded"
    return None
