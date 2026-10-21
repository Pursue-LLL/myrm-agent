"""Tests for allowlist pattern granularity mapping."""

from __future__ import annotations

from app.api.security.allowlist_granularity import (
    nullable_db_field,
    resolve_allowlist_granularity,
)


def test_resolve_pattern_granularity() -> None:
    assert (
        resolve_allowlist_granularity(
            tool_name="bash_code_execute_tool",
            tool_args_hash="",
            command_pattern="npm install *",
        )
        == "pattern"
    )


def test_resolve_exact_before_tool() -> None:
    assert (
        resolve_allowlist_granularity(
            tool_name="bash_code_execute_tool",
            tool_args_hash="abc123",
            command_pattern="",
        )
        == "exact"
    )


def test_resolve_tool_granularity() -> None:
    assert (
        resolve_allowlist_granularity(
            tool_name="bash_code_execute_tool",
            tool_args_hash="",
            command_pattern="",
        )
        == "tool"
    )


def test_nullable_db_field() -> None:
    assert nullable_db_field("") is None
    assert nullable_db_field("npm install *") == "npm install *"
