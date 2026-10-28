"""Goal controls shared by the HTTP API and IM commands.

[INPUT]
- myrm_agent_harness.agent.goals.protocols::GoalProvider (POS: Goal persistence and lifecycle)
- app.services.agent.gateway::get_agent_gateway (POS: in-flight session, interrupt signal and drain state)
- app.services.agent.adaptive_wakeup::get_adaptive_wakeup_service (POS: a pause or cancel holds the chat's autonomous wakes, a resume lifts the hold)
- myrm_agent_harness.utils.runtime.cancellation::CancellationRegistry (POS: cancels the running message)
- app.services.agent.goals.unattended::trigger_goal_stream_with_failure_policy (POS: unattended goal continuation stream)

[OUTPUT]
- NON_TERMINAL_GOAL_STATUSES: statuses a goal can still leave
- select_cancellable_goal: the goal a "cancel" / "clear" control acts on
- stop_goal_turn: stop the turn a goal was working on after it was paused or cancelled, and keep background results from waking the chat
- note_goal_resumed: the user put the goal back to work, so autonomous wakes are allowed again
- is_turn_stopping: whether the session's turn was told to stop and has not wound down yet
- wait_for_stopped_turn: let a turn that was told to stop finish winding down before the goal is resumed
- can_start_goal_turn: whether the session can take a new turn now
- continue_resumed_goal: start the turn that carries a just-resumed goal forward

[POS]
One rule per control, so the web card and the IM command agree on which goal they act on, a pause or
cancel stops the work in flight, and a resume actually puts the goal back to work.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.utils.runtime.cancellation import CancellationRegistry, CancelReason

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.unattended import trigger_goal_stream_with_failure_policy

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.protocols import GoalProvider
    from myrm_agent_harness.agent.goals.types import Goal

NON_TERMINAL_GOAL_STATUSES: frozenset[GoalStatus] = frozenset(
    {
        GoalStatus.ACTIVE,
        GoalStatus.PAUSED,
        GoalStatus.PENDING_APPROVAL,
        GoalStatus.BUDGET_LIMITED,
        GoalStatus.NEEDS_HUMAN_REVIEW,
        GoalStatus.QUEUED,
        GoalStatus.WAIT,
    }
)

_STOP_WAIT_SECONDS = 3.0
_STOP_POLL_SECONDS = 0.05


async def select_cancellable_goal(provider: GoalProvider, session_id: str) -> Goal | None:
    """The running goal, else the latest goal while it is still open (paused, in review, waiting, ...)."""
    active = await provider.get_active_goal(session_id)
    if active is not None:
        return active
    latest = await provider.get_latest_goal(session_id)
    if latest is not None and latest.status in NON_TERMINAL_GOAL_STATUSES:
        return latest
    return None


def stop_goal_turn(session_id: str, goal_before_change: Goal) -> bool:
    """Stop the turn a goal was working on, with the signals of the chat Stop button.

    Call it after the goal was paused or cancelled, with the goal as it was before: only an active goal has a
    turn of its own running, so a goal that was waiting, in review or budget-limited leaves the session's
    current turn (a message the user sent meanwhile) alone. The continuation guard sees no active goal and
    starts no further turn. Side effects the turn already produced stay.

    Whatever the goal's state, a pause or cancel is the user's stop: a background result that settles afterwards
    waits for the user instead of waking the chat (the goal may have been waiting on exactly that result).
    """
    get_adaptive_wakeup_service().record_user_stop(session_id)
    if goal_before_change.status is not GoalStatus.ACTIVE:
        return False
    gateway = get_agent_gateway()
    message_id = gateway.get_active_message_id(session_id)
    interrupted = gateway.interrupt_session(session_id)
    cancelled = message_id is not None and CancellationRegistry.cancel(message_id, CancelReason.USER_CANCELLED)
    return interrupted or cancelled


def note_goal_resumed(session_id: str) -> None:
    """The user resumed the goal: the stop that came with its pause no longer holds the chat's wakes back."""
    get_adaptive_wakeup_service().record_human_turn(session_id)


def can_start_goal_turn(session_id: str) -> bool:
    """A new turn may start when the app is not draining and the session has no turn in flight."""
    gateway = get_agent_gateway()
    return not gateway.is_draining and not gateway.is_session_active(session_id)


def is_turn_stopping(session_id: str) -> bool:
    """Whether the turn running in the session was told to stop and has not wound down yet.

    A turn is stopped through its message's cancel token: a chat turn has its own, and a goal turn the server
    starts registers one before its agent is built. A turn without one (the auto-resume after an approval
    timeout) is stopped through the gateway's interrupt signal alone. Either one means it is still winding down.
    """
    gateway = get_agent_gateway()
    message_id = gateway.get_active_message_id(session_id)
    if message_id is not None and CancellationRegistry.is_cancelled(message_id):
        return True
    return gateway.is_session_interrupted(session_id)


async def wait_for_stopped_turn(session_id: str) -> bool:
    """Wait, bounded, while the session's turn winds down after a stop; False if it is still winding down.

    A turn stopped by a pause keeps running for a moment. If the goal turned active in that gap, the stopped
    turn's continuation guard would see an active goal and a cancelled token and pause it again, so a resume
    first lets that turn finish, and is refused when it does not. A turn that was not told to stop (a message
    the user sent meanwhile) does not hold a resume back: it carries the resumed goal on.
    """
    deadline = time.monotonic() + _STOP_WAIT_SECONDS
    while is_turn_stopping(session_id):
        if time.monotonic() >= deadline:
            return False
        await asyncio.sleep(_STOP_POLL_SECONDS)
    return True


async def continue_resumed_goal(session_id: str, provider: GoalProvider, goal_id: str) -> bool:
    """Start the unattended turn for a goal that was just resumed.

    False when nothing was started: the session is busy or the app is draining (the running turn or the
    next message carries the goal on), or the goal is not active.
    """
    if not can_start_goal_turn(session_id):
        return False
    goal = await provider.get_goal(goal_id)
    if goal is None or goal.status is not GoalStatus.ACTIVE:
        return False
    return await trigger_goal_stream_with_failure_policy(
        session_id, goal, provider, on_failure="needs_human_review", context="goal resume"
    )
