"""Internal datatypes for AgentRouter task registry and per-turn execution context.

[POS]
Data models referenced by AgentRouter in router.py and router_commands (_ActiveTask type annotation).
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections.abc import Awaitable, Callable

from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken

from app.channels.types import InboundMessage, ReactionLevel, TopicContext

CleanupFn = Callable[[], Awaitable[None]]


# ── Reaction policy ───────────────────────────────────────────


@dataclasses.dataclass(frozen=True, slots=True)
class ReactionPolicy:
    """Immutable reaction configuration for AgentRouter.

    Three levels:
    - ``OFF``: all automatic reactions disabled.
    - ``SIMPLE``: only completion reaction.
    - ``FULL``: processing reaction on receive + completion reaction on finish
      + auto-remove processing reaction after completion.
    """

    level: ReactionLevel = ReactionLevel.FULL
    processing_emoji: str = "\U0001f440"
    completion_emoji: str = "\u2705"
    failure_emoji: str = "\u274c"

    @property
    def should_processing(self) -> bool:
        return self.level == ReactionLevel.FULL

    @property
    def should_completion(self) -> bool:
        return self.level in {ReactionLevel.SIMPLE, ReactionLevel.FULL}


@dataclasses.dataclass(slots=True)
class _CleanupEntry:
    """Deferred cleanup with monotonic timestamp for TTL eviction."""

    cleanup: CleanupFn
    created_at: float


@dataclasses.dataclass(slots=True)
class _ActiveTask:
    """Running agent task metadata for /stop, /steer, stuck watchdog, and placeholder cleanup.

    ``requester_id`` is the channel-level sender identifier (e.g. Slack user
    id, Telegram user id) of the message that initiated this turn. It is
    captured at task creation time so reaction-based approvals can verify that
    the reacting user is either the original requester or an explicitly
    permitted co-approver.

    ``started_at`` is a monotonic timestamp used by the janitor's stuck-task
    watchdog to detect tasks that exceed ``_STUCK_TASK_TIMEOUT``.
    """

    task: asyncio.Task[None]
    cancel_token: CancellationToken
    channel: str
    chat_id: str
    placeholder_id: str | None
    started_at: float
    requester_id: str = ""
    steering_token: SteeringToken | None = None
    deferred_placeholder: object | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class _RouterExecutionContext:
    """Bindings for one agent turn: resolved user, session keys, topic overrides, and exec message.

    ``exec_msg`` is the post-policy inbound payload (DM: same instance as input; group: resolver output).
    Session flags may update ``exec_msg.metadata`` before this object is constructed.
    """

    user_id: str
    state_key: str
    chat_id: str
    message_id: str | None
    topic_ctx: TopicContext | None
    exec_msg: InboundMessage


@dataclasses.dataclass(slots=True)
class _AgentTurnScratch:
    """Holds mutable execution state for `_handle_merged` outer error handling."""

    placeholder_id: str | None = None
    deferred_placeholder: object | None = None
    completed: bool = False
