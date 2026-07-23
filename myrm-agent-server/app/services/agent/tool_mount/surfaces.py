"""Execution entry surfaces for agent meta-tool mount policy.

[INPUT]
(none — pure enum)

[OUTPUT]
- ExecutionSurface: product entry identifiers for mount policy

[POS]
Surface enum consumed by tool_mount.resolver.resolve_agent_mount.
"""

from __future__ import annotations

from enum import StrEnum


class ExecutionSurface(StrEnum):
    """Product entry point — determines default meta-tool (file/shell) mount."""

    WEB_CHAT = "web_chat"
    WEB_FAST = "web_fast"
    CHANNEL = "channel"
    CRON = "cron"
    KANBAN = "kanban"
    VOICE = "voice"
    EVAL = "eval"
