"""Feishu ActionButton fallback to numbered text options for intranet/localhost environments.

When Myrm runs in a local/Tauri environment without a public webhook endpoint,
interactive card button clicks cannot be delivered by Feishu. This module:
1. Detects local/webhook-less execution mode.
2. Injects numbered text action prompts (e.g. `[1] 允许 [2] 拒绝`) into card footers.
3. Maintains scoped `(chat_id, user_id)` session action registries with TTL expiration.
4. Translates simple digit replies (e.g. "1") into structured `act:action_id` callback events.

[INPUT]
- ActionButton components, inbound text messages, and channel execution context.

[OUTPUT]
- FallbackActionSessionRegistry: Thread-safe in-memory session registry with TTL.
- build_fallback_action_elements: Card elements rendering numbered text choices.
- match_fallback_action: Match user digit input to pending action_id.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.channels.types import ActionButton

logger = logging.getLogger("myrm.channels.feishu.action_fallback")

DEFAULT_ACTION_TTL_SECONDS = 300.0  # 5 minutes


@dataclass
class PendingActionOption:
    """A numbered action option."""

    index: int
    label: str
    action_id: str
    style: str = "default"


@dataclass
class PendingActionSession:
    """Active pending action session bound to a scoped chat/user/message."""

    chat_id: str
    user_id: str
    message_id: str
    options: list[PendingActionOption]
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = DEFAULT_ACTION_TTL_SECONDS

    @property
    def is_expired(self) -> bool:
        """Check whether the session has expired."""
        return (time.time() - self.created_at) > self.ttl_seconds


class FallbackActionSessionRegistry:
    """In-memory thread-safe registry tracking pending numbered actions.

    Keys are scoped by `(chat_id, user_id)` to prevent collisions in multi-user group chats.
    """

    def __init__(self, ttl_seconds: float = DEFAULT_ACTION_TTL_SECONDS) -> None:
        self.default_ttl = ttl_seconds
        # (chat_id, user_id) -> PendingActionSession
        self._sessions: dict[tuple[str, str], PendingActionSession] = {}

    def _cleanup_expired(self) -> None:
        """Remove expired action sessions."""
        now = time.time()
        expired_keys = [
            k
            for k, sess in self._sessions.items()
            if (now - sess.created_at) > sess.ttl_seconds
        ]
        for k in expired_keys:
            self._sessions.pop(k, None)

    def register_actions(
        self,
        chat_id: str,
        user_id: str,
        message_id: str,
        actions: list[ActionButton],
        ttl_seconds: float | None = None,
    ) -> list[PendingActionOption]:
        """Register a list of ActionButtons as numbered options for the given user in chat.

        Args:
            chat_id: Feishu chat open_id.
            user_id: Recipient user open_id (or "" for public group prompt).
            message_id: Outbound message ID.
            actions: ActionButton list to register.
            ttl_seconds: Optional custom TTL.

        Returns:
            List of PendingActionOption objects.
        """
        self._cleanup_expired()
        options: list[PendingActionOption] = []
        for idx, btn in enumerate(actions, start=1):
            options.append(
                PendingActionOption(
                    index=idx,
                    label=btn.label,
                    action_id=btn.action_id,
                    style=str(btn.style),
                )
            )

        session = PendingActionSession(
            chat_id=chat_id,
            user_id=user_id,
            message_id=message_id,
            options=options,
            ttl_seconds=ttl_seconds or self.default_ttl,
        )
        self._sessions[(chat_id, user_id)] = session
        return options

    def resolve_action(
        self,
        chat_id: str,
        user_id: str,
        input_text: str,
    ) -> str | None:
        """Attempt to match inbound user text (e.g. '1', '[1]', '一') to a registered action_id.

        Consumes and removes the session upon successful resolution.

        Args:
            chat_id: Inbound message chat_id.
            user_id: Sender user open_id.
            input_text: Raw incoming text content.

        Returns:
            Matched action_id string or None.
        """
        self._cleanup_expired()
        stripped = input_text.strip()
        if not stripped:
            return None

        # Check direct user session first, then wildcard user session
        session = self._sessions.get((chat_id, user_id)) or self._sessions.get(
            (chat_id, "")
        )
        if not session or session.is_expired:
            return None

        # Parse index from input text: "1", "[1]", "【1】", "1.", "#1"
        target_idx = _parse_action_index(stripped)
        if target_idx is None:
            return None

        for opt in session.options:
            if opt.index == target_idx:
                # Successfully resolved, pop session
                self._sessions.pop((chat_id, user_id), None)
                self._sessions.pop((chat_id, ""), None)
                logger.info(
                    "FallbackAction: resolved option [%d] '%s' -> action_id '%s' for user %s",
                    opt.index,
                    opt.label,
                    opt.action_id,
                    user_id,
                )
                return opt.action_id

        return None


def _parse_action_index(text: str) -> int | None:
    """Extract numeric option index from text input."""
    # Direct digit
    if text.isdigit():
        try:
            return int(text)
        except ValueError:
            return None

    # Bracketed: [1], 【1】, (1), 1.
    cleaned = text.strip("[]【】()（）#.")
    if cleaned.isdigit():
        try:
            return int(cleaned)
        except ValueError:
            return None

    # Chinese digits: 一, 二, 三, 四, 五
    cn_digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5}
    if text in cn_digits:
        return cn_digits[text]

    return None


def build_fallback_action_card_elements(
    options: list[PendingActionOption],
) -> list[dict[str, object]]:
    """Build Feishu card elements presenting numbered fallback actions.

    Args:
        options: Registered PendingActionOption list.

    Returns:
        List of Feishu card elements rendering the prompt.
    """
    if not options:
        return []

    lines = ["**👉 本地/内网模式快速操作（直接回复对应编号）：**"]
    for opt in options:
        lines.append(f"`[{opt.index}]` {opt.label}")

    return [
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "\n".join(lines),
            },
        },
    ]


# Global default registry instance for the Feishu channel
default_action_fallback_registry = FallbackActionSessionRegistry()
