"""Row converters turn raw SQLite tuples into typed models without losing or inventing values."""

from __future__ import annotations

from datetime import UTC

import pytest
from pydantic import ValidationError

from myrm_agent_harness.toolkits.memory.relational._converters import (
    PROCEDURAL_COLUMNS,
    row_to_pending,
    row_to_procedural,
    row_to_profile,
)
from myrm_agent_harness.toolkits.memory.types import MemoryStatus, MemoryType, RuleSource, ToolRulePriority

_STAMP = "2026-01-02T03:04:05+00:00"


def _profile_row(namespaces: str | None = '["ns-a", "ns-b"]') -> tuple[object, ...]:
    return ("p1", "u1", "language", "zh", "ns-a", namespaces, None, "web", None, None, _STAMP, _STAMP)


def _rule_row(**overrides: object) -> tuple[object, ...]:
    """A procedural row laid out by ``PROCEDURAL_COLUMNS``, with named columns replaced."""
    values: dict[str, object] = {
        "id": "r1",
        "user_id": "u1",
        "content": "When: a -> Do: b",
        "trigger_text": "a",
        "action_text": "b",
        "is_active": 1,
        "trigger_keywords": '["alpha"]',
        "source": "agent_self",
        "metadata": '{"k": "v"}',
        "primary_namespace": "ns-a",
        "namespaces": '["ns-a"]',
        "agent_id": None,
        "channel_id": None,
        "conversation_id": None,
        "task_id": None,
        "tool_name": "shell",
        "tool_rule_priority": "high",
        "access_count": 3,
        "last_accessed_at": None,
        "created_at": _STAMP,
        "updated_at": _STAMP,
        "is_user_locked": 1,
        "expected_valid_days": 7,
    }
    values.update(overrides)
    return tuple(values[column.strip()] for column in PROCEDURAL_COLUMNS.split(","))


def _pending_row(status: str = "pending") -> tuple[object, ...]:
    return ("q1", "u1", "semantic", "likes tea", '{"k": "v"}', "c1", "m1", status, _STAMP, None, "correct", "t1", "old")


class TestProfileRow:
    def test_reads_scope_and_json_namespaces(self) -> None:
        entry = row_to_profile(_profile_row())

        assert (entry.id, entry.key, entry.value) == ("p1", "language", "zh")
        assert entry.scope.primary_namespace == "ns-a"
        assert entry.scope.namespaces == ["ns-a", "ns-b"]
        assert entry.scope.channel_id == "web"
        assert entry.created_at.tzinfo == UTC

    def test_missing_namespaces_is_empty(self) -> None:
        assert row_to_profile(_profile_row(namespaces=None)).scope.namespaces == []


class TestProceduralRow:
    def test_reads_every_typed_column(self) -> None:
        rule = row_to_procedural(_rule_row())

        assert (rule.trigger, rule.action) == ("a", "b")
        assert rule.status == MemoryStatus.ACTIVE
        assert rule.source == RuleSource.AGENT_SELF
        assert rule.tool_rule_priority == ToolRulePriority.HIGH
        assert rule.scope.namespaces == ["ns-a"]
        assert rule.trigger_keywords == ["alpha"]
        assert rule.metadata == {"k": "v"}
        assert rule.access_count == 3
        assert rule.expected_valid_days == 7
        assert rule.is_user_locked is True

    def test_empty_columns_take_defaults(self) -> None:
        rule = row_to_procedural(
            _rule_row(
                source=None,
                tool_rule_priority=None,
                access_count=0,
                expected_valid_days=None,
                is_user_locked=0,
            )
        )

        assert rule.source == RuleSource.USER_EXTRACTED
        assert rule.tool_rule_priority == ToolRulePriority.NORMAL
        assert rule.access_count == 0
        assert rule.expected_valid_days is None
        assert rule.is_user_locked is False

    def test_unknown_tool_priority_falls_back_to_normal(self) -> None:
        assert row_to_procedural(_rule_row(tool_rule_priority="urgent")).tool_rule_priority == ToolRulePriority.NORMAL

    def test_inactive_row_is_disabled(self) -> None:
        assert row_to_procedural(_rule_row(is_active=0)).status == MemoryStatus.DISABLED


class TestPendingRow:
    @pytest.mark.parametrize("status", ["pending", "approved", "rejected", "resolved"])
    def test_reads_status_and_target(self, status: str) -> None:
        record = row_to_pending(_pending_row(status))

        assert record.status == status
        assert record.memory_type == MemoryType.SEMANTIC
        assert record.memory_data == {"k": "v"}
        assert (record.target_memory_id, record.target_content) == ("t1", "old")

    def test_unknown_status_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            row_to_pending(_pending_row("expired"))
