"""Why a turn stopped: the stored shape of a stop reason, and which of two reasons wins.

[INPUT]
- (none; pure functions over plain dicts)

[OUTPUT]
- normalize_stop_reason: the stored shape (``code`` / ``category`` / ``message``, plus ``detail`` when it is not empty)
- stop_reason_priority: how strongly a stop reason code explains why a turn ended
- merge_stop_reason: the reason to keep when another arrives (higher priority wins, a later one wins a tie)
- step_item_text: the first non-blank ``text`` of a progress step's ``items``

[POS]
The chat stream collector (services), the cron runner (core) and the Runs Hub (api) all store and read the
same ``stopReason`` shape; this is the one definition they share.
"""

from __future__ import annotations

_CATEGORIES = frozenset({"limit", "cancelled", "error", "other"})
_LIMIT_CODES = frozenset({"iteration_limit_reached", "engine_limit_reached"})


def stop_reason_priority(code: str) -> int:
    if code in _LIMIT_CODES:
        return 40
    if code == "agent_cancelled":
        return 30
    if code == "error":
        return 20
    return 10


def normalize_stop_reason(raw: object) -> dict[str, object] | None:
    """Return the stored shape of ``raw``, or ``None`` when it names no code."""
    if not isinstance(raw, dict):
        return None
    code_obj = raw.get("code")
    if not isinstance(code_obj, str) or not code_obj.strip():
        return None
    code = code_obj.strip()
    category_obj = raw.get("category")
    category = category_obj if isinstance(category_obj, str) and category_obj in _CATEGORIES else "other"
    message_obj = raw.get("message")
    message = message_obj.strip() if isinstance(message_obj, str) and message_obj.strip() else code.replace("_", " ")
    normalized: dict[str, object] = {"code": code, "category": category, "message": message}
    detail_obj = raw.get("detail")
    if isinstance(detail_obj, dict):
        detail = {key: value for key, value in detail_obj.items() if isinstance(key, str)}
        if detail:
            normalized["detail"] = detail
    return normalized


def merge_stop_reason(current: dict[str, object] | None, incoming: dict[str, object]) -> dict[str, object] | None:
    """Return the reason to keep once ``incoming`` arrives; an ``incoming`` that names no code changes nothing."""
    normalized = normalize_stop_reason(incoming)
    if normalized is None:
        return current
    if current is None or _priority(normalized) >= _priority(current):
        return normalized
    return current


def step_item_text(items: object) -> str | None:
    """Return the first non-blank ``text`` among a progress step's ``items``."""
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def _priority(reason: dict[str, object]) -> int:
    code = reason.get("code")
    return stop_reason_priority(code) if isinstance(code, str) else 0
