"""Row converters turn raw SQLite tuples into typed models without losing or inventing values."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from myrm_agent_harness.toolkits.memory.relational._converters import (
    PROCEDURAL_COLUMNS,
    row_to_pending,
    row_to_procedural,
    row_to_profile,
)
from myrm_agent_harness.toolkits.memory.types import (
    MemoryStatus,
    MemoryType,
    ProceduralMemory,
    RuleSource,
    ToolRulePriority,
)

_STAMP = "2026-01-02T03:04:05+00:00"
_ACCESSED = "2026-01-03T04:05:06+00:00"
_UPDATED = "2026-01-05T06:07:08+00:00"


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
        "source": "agent_self",
        "metadata": '{"k": "v"}',
        "primary_namespace": "ns-a",
        "namespaces": '["ns-a"]',
        "agent_id": "agent-1",
        "channel_id": "chan-1",
        "conversation_id": "conv-1",
        "task_id": "task-1",
        "tool_name": "shell",
        "tool_rule_priority": "high",
        "access_count": 3,
        "last_accessed_at": _ACCESSED,
        "created_at": _STAMP,
        "updated_at": _UPDATED,
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

        assert (rule.id, rule.user_id, rule.content) == ("r1", "u1", "When: a -> Do: b")
        assert (rule.trigger, rule.action) == ("a", "b")
        assert rule.status == MemoryStatus.ACTIVE
        assert rule.source == RuleSource.AGENT_SELF
        assert rule.metadata == {"k": "v"}
        assert rule.scope.primary_namespace == "ns-a"
        assert rule.scope.namespaces == ["ns-a"]
        assert (rule.scope.agent_id, rule.scope.channel_id) == ("agent-1", "chan-1")
        assert (rule.scope.conversation_id, rule.scope.task_id) == ("conv-1", "task-1")
        assert rule.tool_name == "shell"
        assert rule.tool_rule_priority == ToolRulePriority.HIGH
        assert rule.access_count == 3
        assert rule.last_accessed_at == datetime.fromisoformat(_ACCESSED)
        assert (rule.created_at, rule.updated_at) == (datetime.fromisoformat(_STAMP), datetime.fromisoformat(_UPDATED))
        assert rule.is_user_locked is True
        assert rule.expected_valid_days == 7

    def test_empty_columns_take_defaults(self) -> None:
        rule = row_to_procedural(
            _rule_row(
                source=None,
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
                tool_name=None,
                tool_rule_priority=None,
                access_count=0,
                last_accessed_at=None,
                expected_valid_days=None,
                is_user_locked=0,
            )
        )

        assert rule.source == RuleSource.USER_EXTRACTED
        assert rule.scope.namespaces == []
        assert (rule.scope.agent_id, rule.scope.channel_id, rule.scope.conversation_id, rule.scope.task_id) == (
            None,
            None,
            None,
            None,
        )
        assert rule.tool_name is None
        assert rule.tool_rule_priority == ToolRulePriority.NORMAL
        assert rule.access_count == 0
        assert rule.last_accessed_at is None
        assert rule.expected_valid_days is None
        assert rule.is_user_locked is False

    @pytest.mark.parametrize(
        ("column", "read"),
        [
            ("metadata", lambda rule: rule.metadata == {}),
            ("namespaces", lambda rule: rule.scope.namespaces == []),
            ("agent_id", lambda rule: rule.scope.agent_id is None),
            ("channel_id", lambda rule: rule.scope.channel_id is None),
            ("conversation_id", lambda rule: rule.scope.conversation_id is None),
            ("task_id", lambda rule: rule.scope.task_id is None),
            ("tool_name", lambda rule: rule.tool_name is None),
            ("last_accessed_at", lambda rule: rule.last_accessed_at is None),
        ],
    )
    def test_one_empty_column_is_empty_whatever_its_neighbours_hold(
        self, column: str, read: Callable[[ProceduralMemory], bool]
    ) -> None:
        assert read(row_to_procedural(_rule_row(**{column: None})))

    @pytest.mark.parametrize(("locked", "valid_days"), [(1, None), (0, 7)])
    def test_the_lock_and_the_validity_window_each_read_their_own_column(
        self, locked: int, valid_days: int | None
    ) -> None:
        rule = row_to_procedural(_rule_row(is_user_locked=locked, expected_valid_days=valid_days))

        assert (rule.is_user_locked, rule.expected_valid_days) == (bool(locked), valid_days)

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
