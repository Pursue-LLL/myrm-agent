"""Whitelist target resolution for outbound notifications.

[INPUT]
- .types::NotifyTarget (POS: outbound notification data types)

[OUTPUT]
- resolve_notify_target: Map channel/target input to an allowed NotifyTarget.

[POS]
Target resolution for agent-initiated outbound channel notifications.
"""

from __future__ import annotations

from .types import NotifyTarget


def resolve_notify_target(
    channel: str,
    target: str,
    allowed: tuple[NotifyTarget, ...],
) -> NotifyTarget | None:
    """Resolve user-provided channel/target to an allowed NotifyTarget.

    Resolution strategy:
    1. Exact match: channel + target both match.
    2. Channel-only: channel matches, target omitted → first match for that channel.
    3. Single-target: only one target configured → use it regardless of input.
    4. Target-only: match by recipient_id or label.
    """
    if not allowed:
        return None

    if len(allowed) == 1 and not channel and not target:
        return allowed[0]

    if channel and target:
        for entry in allowed:
            if entry.channel == channel and entry.recipient_id == target:
                return entry
        return None

    if channel:
        for entry in allowed:
            if entry.channel == channel:
                return entry
        channel_lower = channel.lower()
        for entry in allowed:
            if entry.channel.lower() == channel_lower:
                return entry
        return None

    if len(allowed) == 1:
        return allowed[0]

    if target:
        for entry in allowed:
            if entry.recipient_id == target or entry.label == target:
                return entry

    return None
