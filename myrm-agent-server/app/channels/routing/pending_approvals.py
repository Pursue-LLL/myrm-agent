"""Tool approvals a chat is waiting on, and the timer that ends each wait.

[INPUT]
- myrm_agent_harness.agent.middlewares.approval.scheduler::ApprovalTimeoutScheduler (POS: idempotent timeout-vs-answer claim and audit record)
- app.channels.routing.router_keys::routing_session_key (POS: the chat-wide key the resume claim is made under)
- app.channels.types::ApprovalExpiry, InboundMessage, TopicContext (POS: the wait's time limit; the message a timeout resume is derived from; the agent binding a turn runs under)

[OUTPUT]
- METADATA_APPROVAL_TIMED_OUT_KEY: marks a resume turn that the timeout, not a person, answered
- PendingApproval: one open approval request of a chat
- session_agent_id: the agent whose session a turn runs in, the identity of the run an approval belongs to
- PendingApprovals: the router's registry of them, owner of the timer of each

[POS]
A turn that stops at a tool approval leaves its chat waiting. Whoever ends the wait (the chat's answer, ``/stop``,
the janitor, the timeout, or a turn that starts in the session the request waits in, which takes the run it belongs
to away) goes through this registry, so the chat, the approval card and the timer never disagree about whether a
request is open. The timeout reports through ``on_expire``; the router resumes the run then as an ordinary turn, the
same way it resumes one a person answered, so the resumed run is visible to ``/stop``.
The timer's claim key is chat-wide (``channel:peer``), the key the manual resume claims under: one chat holds one
timer at a time, so when two forum topics wait the later request's timer replaces the earlier one's, which then waits
for an answer without a time limit.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable

from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

from app.channels.routing.router_keys import routing_session_key
from app.channels.types import ApprovalExpiry, InboundMessage, TopicContext

METADATA_APPROVAL_TIMED_OUT_KEY = "approval_timed_out"

# Set per message from the chat's session state when a turn starts; a copy from an earlier turn must not outlive it.
_SESSION_SCOPED_METADATA = ("yolo_state", "personality_style", "force_new_epoch")


def session_agent_id(topic_context: TopicContext | None) -> str | None:
    """The agent whose session a turn runs in (``None``: the default agent), as the executor resolves it.

    The agent is a dimension of the session key, so a turn of another agent runs in another session.
    """
    if topic_context is None or topic_context.identity_revoked:
        return None
    return topic_context.agent_id


@dataclasses.dataclass(frozen=True, slots=True)
class PendingApproval:
    """One open approval request of a chat.

    ``card_message_id`` is the platform id of the approval card, ``""`` when the channel returned none. ``message`` is
    the message of the turn that asked, ``user_id`` the identity that turn ran as: a resume runs as the same sender.
    ``agent_id`` is the agent whose session the asking run belongs to (see ``session_agent_id``).
    """

    card_message_id: str
    message: InboundMessage
    user_id: str
    agent_id: str | None = None

    @property
    def timer_key(self) -> str:
        """The chat-wide key the timeout and a manual resume claim the request under."""
        return routing_session_key(self.message.channel, self.message.chat_id or self.message.sender_id)

    def resume_message(self, resume_value: dict[str, object]) -> InboundMessage:
        """The message that resumes the asking turn's run with ``resume_value``, as the timeout's answer."""
        metadata = {k: v for k, v in self.message.metadata.items() if k not in _SESSION_SCOPED_METADATA}
        metadata["is_resume"] = True
        metadata[METADATA_APPROVAL_TIMED_OUT_KEY] = True
        return dataclasses.replace(
            self.message,
            content="",
            media=(),
            context_messages=(),
            message_id=None,
            user_id=self.user_id,
            resume_value=resume_value,
            metadata=metadata,
        )


OnExpire = Callable[[str, PendingApproval, dict[str, object]], Awaitable[None]]


class PendingApprovals:
    """Open approval requests by router state key, each with the timer that ends its wait."""

    def __init__(self, on_expire: OnExpire) -> None:
        self._open: dict[str, PendingApproval] = {}
        self._timer_owner: dict[str, str] = {}
        self._on_expire = on_expire

    def __contains__(self, state_key: str) -> bool:
        return state_key in self._open

    def get(self, state_key: str) -> PendingApproval | None:
        """The chat's open request; None when it waits on nothing."""
        return self._open.get(state_key)

    def card_message_id(self, state_key: str) -> str | None:
        """The approval card's message id (``""`` when it has none); None when the chat waits on no approval."""
        pending = self._open.get(state_key)
        return pending.card_message_id if pending is not None else None

    def register(self, state_key: str, pending: PendingApproval, expiry: ApprovalExpiry | None) -> None:
        """Open ``pending`` for the chat, replacing an earlier request, and start its timer when it has a time limit."""
        self._open[state_key] = pending
        scheduler = ApprovalTimeoutScheduler.get()
        timer_key = pending.timer_key
        if expiry is None:
            # No timer to claim the request, so the next answer must not be refused as already resolved.
            self._timer_owner.pop(timer_key, None)
            scheduler.cancel(timer_key)
            scheduler.reopen(timer_key)
            return

        async def on_timeout(resume_value: dict[str, object]) -> None:
            if self._open.get(state_key) is not pending:
                return
            del self._open[state_key]
            self._timer_owner.pop(timer_key, None)
            try:
                await self._on_expire(state_key, pending, resume_value)
            except Exception:
                # The timer claimed the request before reporting; a failed report leaves the run suspended, so the
                # claim goes back and the chat's own answer is not refused as already resolved.
                scheduler.reopen(timer_key)
                raise

        self._timer_owner[timer_key] = state_key
        scheduler.schedule(
            key=timer_key,
            timeout_seconds=expiry.seconds,
            behavior=expiry.behavior,
            resume_callback=on_timeout,
        )

    def pop(self, state_key: str) -> PendingApproval | None:
        """End the chat's wait (answered, stopped, reaped) and its timer; None when it waited on nothing."""
        pending = self._open.pop(state_key, None)
        if pending is not None and self._timer_owner.get(pending.timer_key) == state_key:
            del self._timer_owner[pending.timer_key]
            ApprovalTimeoutScheduler.get().cancel(pending.timer_key)
        return pending

    def clear(self) -> None:
        """End every wait and every timer (router shutdown)."""
        scheduler = ApprovalTimeoutScheduler.get()
        for timer_key in self._timer_owner:
            scheduler.cancel(timer_key)
        self._timer_owner.clear()
        self._open.clear()
