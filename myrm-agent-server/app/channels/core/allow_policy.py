"""Inbound access control policy for channels.

Determines whether an inbound message should be processed based on
sender identity, chat type, bot status, and configured policies.

Preset Policies:
- OPEN_POLICY: Allow all DM and group messages (no mention required)
- SELECTIVE_POLICY: Allow all DMs, group messages require mention
- STRICT_POLICY: All messages require mention (DMs and groups)

[INPUT]
- app.channels.types::InboundMessage (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- ChatPolicy: Policy for accepting messages from a specific chat type.
- FilterReason: Enum of reasons why a message was rejected.
- ChatPolicyOverride: Per-chat policy overrides for specific chat IDs.
- AllowPolicy: Access control configuration for a channel.

[POS]
Inbound access control policy for channels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum

from app.channels.types import InboundMessage

logger = logging.getLogger(__name__)


class ChatPolicy(Enum):
    """Policy for accepting messages from a specific chat type."""

    ALLOW = "allow"
    DENY = "deny"
    MENTION_ONLY = "mention_only"


class FilterReason(Enum):
    """Reason why an inbound message was rejected by AllowPolicy.

    Returned by ``AllowPolicy.evaluate()`` for precise diagnostics.
    """

    DENYLISTED = "denylisted"
    NOT_ALLOWLISTED = "not_allowlisted"
    BOT_DENIED = "bot_denied"
    BOT_NOT_MENTIONED = "bot_not_mentioned"
    CHAT_DENIED = "chat_denied"
    CHAT_NOT_MENTIONED = "chat_not_mentioned"


@dataclass(frozen=True, slots=True)
class ChatPolicyOverride:
    """Per-chat policy overrides.

    Fields set to None inherit the global AllowPolicy value.
    """

    group_policy: ChatPolicy | None = None
    bot_policy: ChatPolicy | None = None


@dataclass(frozen=True, slots=True)
class AllowPolicy:
    """Access control configuration for a channel.

    Evaluation order:
        1. denylist  — reject if sender is denylisted
        2. bot check — if sender is a bot, apply bot_policy
                       (admitted bots bypass the human allowlist)
        3. allowlist — reject if sender is not in allowlist (when set)
        4. chat policy — apply dm_policy or group_policy based on chat type
    """

    allowlist: frozenset[str] = frozenset()
    denylist: frozenset[str] = frozenset()
    dm_policy: ChatPolicy = ChatPolicy.ALLOW
    group_policy: ChatPolicy = ChatPolicy.MENTION_ONLY
    bot_policy: ChatPolicy = ChatPolicy.DENY
    chat_overrides: dict[str, ChatPolicyOverride] = field(default_factory=dict)

    def evaluate(self, msg: InboundMessage) -> FilterReason | None:
        """Evaluate whether an inbound message passes the access policy.

        Returns None if allowed, or a FilterReason explaining the rejection.
        """
        sender = msg.sender_id

        if sender in self.denylist:
            return FilterReason.DENYLISTED

        override = self.chat_overrides.get(msg.chat_id or "") if msg.chat_id else None
        effective_bot_policy = (override.bot_policy if override and override.bot_policy is not None else self.bot_policy)

        if msg.is_bot:
            if effective_bot_policy == ChatPolicy.DENY:
                return FilterReason.BOT_DENIED
            if effective_bot_policy == ChatPolicy.MENTION_ONLY and not msg.mentioned:
                return FilterReason.BOT_NOT_MENTIONED
            return None

        if self.allowlist and sender not in self.allowlist:
            return FilterReason.NOT_ALLOWLISTED

        effective_group_policy = (override.group_policy if override and override.group_policy is not None else self.group_policy)
        policy = effective_group_policy if msg.is_group else self.dm_policy

        if policy == ChatPolicy.DENY:
            return FilterReason.CHAT_DENIED
        if policy == ChatPolicy.MENTION_ONLY and not msg.mentioned:
            return FilterReason.CHAT_NOT_MENTIONED

        return None


OPEN_POLICY = AllowPolicy(
    dm_policy=ChatPolicy.ALLOW,
    group_policy=ChatPolicy.ALLOW,
)

SELECTIVE_POLICY = AllowPolicy(
    dm_policy=ChatPolicy.ALLOW,
    group_policy=ChatPolicy.MENTION_ONLY,
)

STRICT_POLICY = AllowPolicy(
    dm_policy=ChatPolicy.MENTION_ONLY,
    group_policy=ChatPolicy.MENTION_ONLY,
)
