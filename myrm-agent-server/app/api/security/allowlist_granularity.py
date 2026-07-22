"""Allowlist entry granularity helpers for REST API responses.

[INPUT]
- UserToolAllowlist column values from app.database.models (POS: 安全 allowlist ORM)

[OUTPUT]
- resolve_allowlist_granularity(): user-facing granularity label
- nullable_db_field(): empty-string DB sentinel → None for harness remove()

[POS]
Server allowlist REST 层粒度映射。与 harness Allowlist.check 四层优先级保持一致。
"""

from __future__ import annotations


def resolve_allowlist_granularity(
    *,
    tool_name: str,
    tool_args_hash: str,
    command_pattern: str,
) -> str:
    """Map persisted allowlist columns to a user-facing granularity label."""
    if command_pattern:
        return "pattern"
    if tool_args_hash:
        return "exact"
    if tool_name:
        return "tool"
    return "permission"


def nullable_db_field(value: str) -> str | None:
    """Convert empty-string DB sentinel back to None for harness remove()."""
    return value or None
