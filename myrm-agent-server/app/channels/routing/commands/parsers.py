"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- parse_yolo_args: Parse YOLO mode arguments.
- parse_personality_args: Parse personality command arguments.
- parse_memory_args: Parse /memory sub-command arguments.
- DenyWithReason: Deny decision carrying a user-supplied reason for Agent course-correction.
- normalize_approval_emoji: Strip variation selectors (FE0E/FE0F) and Fitzpatrick skin-tone modifiers.
- parse_approval_command: Parse approval commands into the three-tier decision model.
- is_explicit_approval_command: Whether ``content`` is an explicit /approve, /approve-always, /deny, or /batch.

[POS]
IM 斜杠命令域的子模块；由 app/channels/routing/commands/__init__.py 聚合导出。
"""

from __future__ import annotations

import dataclasses
import logging
import re
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def parse_yolo_args(raw_args: str) -> tuple[str, int | None] | None:
    """Parse YOLO mode arguments.

    Supported formats:
    - ""              -> ("toggle", None)
    - "toggle"        -> ("toggle", None)
    - "on"            -> ("on", None)
    - "on 3600"       -> ("on", 3600)
    - "off"           -> ("off", None)
    - "status"        -> ("status", None)

    Returns:
        Tuple of (action, timeout_seconds) or None if invalid.
    """
    parts = raw_args.strip().lower().split()
    if not parts:
        return ("toggle", None)
    if len(parts) == 1:
        action = parts[0]
        if action in ("on", "off", "toggle", "status"):
            return (action, None)
        return None
    if len(parts) == 2 and parts[0] == "on":
        try:
            timeout = int(parts[1])
            if timeout <= 0:
                return None
            return ("on", timeout)
        except ValueError:
            return None
    return None


def parse_personality_args(raw_args: str) -> str:
    """Parse personality command arguments.

    Returns:
        Style name or "list" if no argument given.
    """
    style = raw_args.strip().lower()
    return style if style else "list"


MemoryAction = Literal["pending", "approve", "reject", "approve_all"]


def parse_memory_args(raw_args: str) -> tuple[MemoryAction, str | None]:
    """Parse /memory sub-command arguments.

    Supported formats:
    - ""                    -> ("pending", None)
    - "pending"             -> ("pending", None)
    - "approve <id>"        -> ("approve", "<id>")
    - "reject <id>"         -> ("reject", "<id>")
    - "approve all"         -> ("approve_all", None)

    Returns:
        Tuple of (action, memory_id_or_none).
    """
    parts = raw_args.strip().split(maxsplit=1)
    if not parts:
        return ("pending", None)

    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if action == "pending":
        return ("pending", None)

    if action == "approve":
        if rest.lower() == "all":
            return ("approve_all", None)
        return ("approve", rest) if rest else ("pending", None)

    if action == "reject":
        return ("reject", rest) if rest else ("pending", None)

    return ("pending", None)


# ---------------------------------------------------------------------------
# Approval decision model
# ---------------------------------------------------------------------------
#
# Three-tier decision aligning with langgraph interrupt() resume semantics and
# harness `_batch_decisions` allow-always allowlist support:
#   - allow_once   : approve current invocation only
#   - allow_always : approve and persist into the user's allowlist (skip future ASK)
#   - deny         : reject current invocation
#
# Reaction emoji mapping (after Unicode normalization):
#   👍 / ❤ / ✅ / 🤝 / 💪    -> allow_once
#   ♾ / ⭐                    -> allow_always
#   👎 / ❌ / 🚫               -> deny
#
# Slash commands & natural shortcuts mirror the three tiers:
#   /approve, 1, y, yes, ok, 同意, 可以, 没问题, 好的, 是 -> allow_once
#   /approve-always, /always, !y, 1!, 永远允许, 总是允许    -> allow_always
#   /deny, 2, n, no, d, deny, r, reject, 拒绝, 不行, 不需要 -> deny
#
# Batch tokens ('/batch a,aa,d'):
#   a / approve            -> allow_once
#   aa / always            -> allow_always
#   d / deny / r / reject  -> deny

ApprovalDecision = Literal["allow_once", "allow_always", "deny"]
_APPROVAL_DECISION_VALUES: frozenset[str] = frozenset(get_args(ApprovalDecision))

_MAX_DENY_REASON_LENGTH = 280


@dataclasses.dataclass(frozen=True, slots=True)
class DenyWithReason:
    """Deny decision carrying a user-supplied reason for Agent course-correction.

    When the user types ``/deny <reason>`` in an IM channel, the reason is
    captured here and later injected into the harness ``guidance`` field so
    the Agent can adapt rather than blindly retrying the denied action.
    """

    reason: str


_VARIATION_SELECTOR_RE = re.compile(r"[\uFE0E\uFE0F]")
_FITZPATRICK_RE = re.compile(r"[\U0001F3FB-\U0001F3FF]")

_APPROVE_ONCE_EMOJIS: frozenset[str] = frozenset({"\U0001f44d", "\u2764", "\u2705", "\U0001f91d", "\U0001f4aa"})
_APPROVE_ALWAYS_EMOJIS: frozenset[str] = frozenset({"\u267e", "\u2b50"})
_DENY_EMOJIS: frozenset[str] = frozenset({"\U0001f44e", "\u274c", "\U0001f6ab"})

_APPROVE_ONCE_TEXT: frozenset[str] = frozenset(
    {
        "/approve",
        "1",
        "y",
        "yes",
        "a",
        "approve",
        "ok",
        "same",
        "'s",
        "没问题",
        "可以",
        "是",
        "同意",
        "好的",
    }
)
_APPROVE_ALWAYS_TEXT: frozenset[str] = frozenset(
    {
        "/approve-always",
        "/always",
        "!y",
        "1!",
        "aa",
        "永远允许",
        "总是允许",
        "一直允许",
    }
)
_DENY_TEXT: frozenset[str] = frozenset(
    {
        "/deny",
        "2",
        "n",
        "no",
        "d",
        "deny",
        "r",
        "reject",
        "拒绝",
        "不行",
        "不需要",
    }
)


def normalize_approval_emoji(value: str) -> str:
    """Strip variation selectors (FE0E/FE0F) and Fitzpatrick skin-tone modifiers.

    Ensures '👍' and '👍🏼' and '👍️' all collapse to the same key so emoji matching
    is reaction-source agnostic. Whitespace is also trimmed.
    """
    cleaned = _VARIATION_SELECTOR_RE.sub("", value.strip())
    return _FITZPATRICK_RE.sub("", cleaned)


def parse_approval_command(
    content: str,
) -> ApprovalDecision | DenyWithReason | list[ApprovalDecision] | None:
    """Parse approval commands into the three-tier decision model.

    Supports slash commands (/approve, /approve-always, /deny), natural shortcuts
    (1, 2, y, n, ok, etc.), emoji reactions (👍/♾/👎 with skin-tone & VS-16 normalisation),
    and batch mode (/batch a,aa,d).

    ``/deny <reason>`` captures trailing text as the deny reason, capped at
    280 characters, and returns a ``DenyWithReason`` so the reason can be
    relayed to the Agent via the harness ``guidance`` field.

    Returns:
        - ``"allow_once" | "allow_always" | "deny"`` for a single decision
        - ``DenyWithReason`` for deny with a user-supplied reason
        - ``list[ApprovalDecision]`` for batch decisions
        - ``None`` if not an approval command
    """
    cmd = content.strip()

    normalized = normalize_approval_emoji(cmd)
    if normalized in _APPROVE_ALWAYS_EMOJIS:
        return "allow_always"
    if normalized in _APPROVE_ONCE_EMOJIS:
        return "allow_once"
    if normalized in _DENY_EMOJIS:
        return "deny"

    cmd_lower = cmd.lower()

    if cmd_lower in _APPROVE_ALWAYS_TEXT:
        return "allow_always"
    if cmd_lower in _APPROVE_ONCE_TEXT:
        return "allow_once"
    if cmd_lower in _DENY_TEXT:
        return "deny"
    if cmd_lower.startswith("/deny "):
        reason = cmd[len("/deny ") :].strip()[:_MAX_DENY_REASON_LENGTH].strip()
        return DenyWithReason(reason=reason) if reason else "deny"

    if cmd_lower.startswith("/batch "):
        batch_spec = cmd_lower[7:].strip()
        if not batch_spec:
            return None

        decisions: list[ApprovalDecision] = []
        for raw_token in batch_spec.split(","):
            token = raw_token.strip()
            if token in ("a", "approve"):
                decisions.append("allow_once")
            elif token in ("aa", "always", "approve-always"):
                decisions.append("allow_always")
            elif token in ("d", "deny", "r", "reject"):
                decisions.append("deny")
            else:
                return None

        return decisions if decisions else None

    return None


def is_explicit_approval_command(content: str) -> bool:
    """Whether ``content`` is an explicit /approve, /approve-always, /deny, or /batch."""
    cmd = content.strip().lower()
    return cmd in ("/approve", "/approve-always", "/always", "/deny") or cmd.startswith("/deny ") or cmd.startswith("/batch ")
