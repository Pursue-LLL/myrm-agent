"""Topic routing types: draft-review mode, identity scope and per-topic configuration.

[INPUT]
- channels.types.thread_sharing::ThreadSharingMode (POS: thread history sharing mode)

[OUTPUT]
- TopicContext: per-topic routing configuration carried with inbound messages
- ReplyMode, DraftTimeoutAction: draft-review delivery policy
- IdentityScopeMode: team-shared identity scope of a topic binding

[POS]
Forum-topic binding types consumed by the router and policy resolver; zero I/O,
pure data.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .thread_sharing import ThreadSharingMode


class ReplyMode(StrEnum):
    """Controls whether outbound channel replies require human review."""

    AUTO = "auto"
    DRAFT_REVIEW = "draft_review"


class DraftTimeoutAction(StrEnum):
    """What happens when a draft review approval expires."""

    AUTO_SEND = "auto_send"
    AUTO_REJECT = "auto_reject"


class IdentityScopeMode(StrEnum):
    """Team-shared identity scope for a topic/channel binding.

    - ``INHERIT`` (default): use the channel baseline shared identity.
    - ``SHARED``: this binding carries its own named shared identity.
    - ``PRIVATE``: independent identity, no baseline inheritance.
    """

    INHERIT = "inherit"
    SHARED = "shared"
    PRIVATE = "private"


@dataclass(frozen=True, slots=True)
class TopicContext:
    """Per-topic configuration for forum-style thread routing.

    When a message arrives from a forum topic (e.g. Telegram supergroup topic),
    this context carries topic-specific overrides that affect session isolation
    and Agent selection.

    ``thread_sharing_mode``: Controls chat history visibility within a thread.
    - ``isolated`` (default): Each user has their own conversation history.
    - ``shared``: All users in the thread share the same conversation history,
      enabling collaborative scenarios (Discord Forum, Telegram Forum Topics).

    ``reply_mode``: Controls outbound message delivery.
    - ``auto`` (default): Agent replies are sent immediately (existing behavior).
    - ``draft_review``: Agent replies are held as drafts for human approval
      before being sent to the channel. Essential for enterprise customer
      service and sales scenarios where AI responses need quality control.

    ``identity_scope`` / ``identity_id`` / ``identity_name``: Team-shared
    identity attached to this binding. ``identity_name`` is display-only;
    routing and audit always use the stable ``identity_id``. ``revoked``
    freezes the identity (routes to the default agent, keeps stored memory
    for a later rejoin) without deleting the binding.

    ``completion_receipts``: Post a delivery receipt in the origin thread
    when a long/delegated task finishes (default on).
    ``stall_nudge``: Proactively @-mention on stalled threads with pending
    items (default off, explicit opt-in).
    """

    topic_id: str
    agent_id: str | None = None
    project_id: str | None = None
    authorized_path: str | None = None
    enabled: bool = True
    bound_at: str | None = None
    matched_by: str | None = None
    thread_sharing_mode: ThreadSharingMode = ThreadSharingMode.ISOLATED
    reply_mode: ReplyMode = ReplyMode.AUTO
    draft_timeout_minutes: int = 5
    draft_timeout_action: DraftTimeoutAction = DraftTimeoutAction.AUTO_REJECT
    personality_style: str | None = None
    identity_scope: IdentityScopeMode = IdentityScopeMode.INHERIT
    identity_id: str | None = None
    identity_name: str | None = None
    identity_revoked: bool = False
    completion_receipts: bool = True
    stall_nudge: bool = False
