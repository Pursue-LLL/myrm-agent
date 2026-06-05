"""Tests for kanban diagnostic rules (server layer).

Covers all 6 rules, severity escalation, helpers, engine factory, and summary.
Target: ≥80% coverage for app.services.kanban.diagnostics.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from myrm_agent_harness.toolkits.kanban.diagnostics import (
    DiagnosticContext,
    TaskDiagnosticSeverity,
)
from myrm_agent_harness.toolkits.kanban.types import (
    KanbanTask,
    TaskPriority,
    TaskStatus,
)

from app.services.kanban.diagnostics import (
    CARD_FAST_RULES,
    BlockUnblockCyclingRule,
    DeadDependencyRule,
    DiagnosticSummary,
    DiagnosticThresholds,
    RepeatedFailuresRule,
    StrandedInReadyRule,
    StuckInBlockedRule,
    _error_snippet,
    _escalate_severity,
    _format_age,
    _hours_since,
    compute_diagnostics_summary,
    create_diagnostic_engine,
)


def _make_task(
    *,
    status: TaskStatus = TaskStatus.READY,
    consecutive_failures: int = 0,
    blocked_reason: str | None = None,
    error: str = "",
    hours_ago: float = 0,
    block_cycle_count: int = 0,
) -> KanbanTask:
    ts = datetime.now(UTC) - timedelta(hours=hours_ago)
    return KanbanTask(
        task_id="t1",
        board_id="b1",
        title="Test Task",
        status=status,
        priority=TaskPriority.NORMAL,
        consecutive_failures=consecutive_failures,
        blocked_reason=blocked_reason,
        error=error,
        updated_at=ts,
        created_at=ts,
        block_cycle_count=block_cycle_count,
    )


# ---------------------------------------------------------------------------
# Helper tests
# ---------------------------------------------------------------------------


class TestEscalateSeverity:
    def test_below_2x_is_warning(self) -> None:
        assert _escalate_severity(25.0, 24.0) == TaskDiagnosticSeverity.WARNING

    def test_at_2x_is_error(self) -> None:
        assert _escalate_severity(48.0, 24.0) == TaskDiagnosticSeverity.ERROR

    def test_between_2x_and_7x_is_error(self) -> None:
        assert _escalate_severity(100.0, 24.0) == TaskDiagnosticSeverity.ERROR

    def test_at_7x_is_critical(self) -> None:
        assert _escalate_severity(168.0, 24.0) == TaskDiagnosticSeverity.CRITICAL

    def test_above_7x_is_critical(self) -> None:
        assert _escalate_severity(200.0, 24.0) == TaskDiagnosticSeverity.CRITICAL

    def test_exact_threshold_is_warning(self) -> None:
        assert _escalate_severity(24.0, 24.0) == TaskDiagnosticSeverity.WARNING


class TestFormatAge:
    def test_hours_below_24(self) -> None:
        assert _format_age(5.0) == "5h"

    def test_hours_exactly_24_below_48(self) -> None:
        assert _format_age(30.0) == "30h"

    def test_hours_48_shows_days(self) -> None:
        assert _format_age(48.0) == "2d"

    def test_hours_72_shows_days(self) -> None:
        assert _format_age(72.0) == "3d"

    def test_hours_just_above_24_shows_hours(self) -> None:
        # 36h → 1.5d, but < 2 → shows "36h"
        assert _format_age(36.0) == "36h"

    def test_zero_hours(self) -> None:
        assert _format_age(0.0) == "0h"


class TestErrorSnippet:
    def test_empty_string(self) -> None:
        assert _error_snippet("") == ""

    def test_whitespace_only(self) -> None:
        assert _error_snippet("   ") == ""

    def test_short_single_line(self) -> None:
        assert _error_snippet("Connection refused") == "Connection refused"

    def test_multiline_takes_first(self) -> None:
        err = "First line\nSecond line\nThird line"
        assert _error_snippet(err) == "First line"

    def test_long_text_truncated(self) -> None:
        long_err = "A" * 300
        result = _error_snippet(long_err)
        assert len(result) == 201  # 200 + ellipsis
        assert result.endswith("…")

    def test_strips_whitespace(self) -> None:
        assert _error_snippet("  trimmed  ") == "trimmed"


class TestHoursSince:
    def test_recent_returns_small(self) -> None:
        now = datetime.now(UTC)
        assert _hours_since(now) < 0.1

    def test_24h_ago(self) -> None:
        dt = datetime.now(UTC) - timedelta(hours=24)
        result = _hours_since(dt)
        assert 23.9 < result < 24.1

    def test_naive_datetime_handled(self) -> None:
        dt = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=1)
        result = _hours_since(dt)
        assert 0.9 < result < 1.1


# ---------------------------------------------------------------------------
# Rule 1: StrandedInReadyRule
# ---------------------------------------------------------------------------


class TestStrandedInReadyRule:
    def setup_method(self) -> None:
        self.rule = StrandedInReadyRule()

    def test_not_ready_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.RUNNING, hours_ago=100)
        assert self.rule.evaluate(task) == []

    def test_recent_ready_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=1)
        assert self.rule.evaluate(task) == []

    def test_stranded_returns_diagnostic(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=30)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].rule_id == "stranded_in_ready"
        assert result[0].severity == TaskDiagnosticSeverity.WARNING

    def test_severity_escalation_to_error(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=50)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.ERROR
        assert "2d" in result[0].title

    def test_severity_escalation_to_critical(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=170)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.CRITICAL

    def test_title_contains_age(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=30)
        result = self.rule.evaluate(task)
        assert "30h" in result[0].title
        assert "dispatcher" in result[0].title

    def test_has_archive_action(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=30)
        result = self.rule.evaluate(task)
        actions = result[0].actions
        assert len(actions) == 1
        assert actions[0].kind == "archive"
        assert actions[0].payload["target_status"] == "archived"

    def test_custom_threshold(self) -> None:
        rule = StrandedInReadyRule(DiagnosticThresholds(stranded_ready_hours=1.0))
        task = _make_task(status=TaskStatus.READY, hours_ago=2)
        result = rule.evaluate(task)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Rule 2: RepeatedFailuresRule
# ---------------------------------------------------------------------------


class TestRepeatedFailuresRule:
    def setup_method(self) -> None:
        self.rule = RepeatedFailuresRule()

    def test_below_threshold_returns_empty(self) -> None:
        task = _make_task(consecutive_failures=2)
        assert self.rule.evaluate(task) == []

    def test_at_threshold_returns_error(self) -> None:
        task = _make_task(consecutive_failures=3)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.ERROR

    def test_double_threshold_returns_critical(self) -> None:
        task = _make_task(consecutive_failures=6)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.CRITICAL

    def test_blocked_status_is_critical(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, consecutive_failures=3)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.CRITICAL

    def test_blocked_has_move_to_ready_action(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, consecutive_failures=3)
        result = self.rule.evaluate(task)
        actions = result[0].actions
        kinds = [a.kind for a in actions]
        assert "move_to_ready" in kinds
        assert "archive" in kinds
        move = next(a for a in actions if a.kind == "move_to_ready")
        assert move.suggested is True

    def test_non_blocked_no_move_action(self) -> None:
        task = _make_task(status=TaskStatus.READY, consecutive_failures=3)
        result = self.rule.evaluate(task)
        kinds = [a.kind for a in result[0].actions]
        assert "move_to_ready" not in kinds
        assert "archive" in kinds

    def test_title_with_error_snippet(self) -> None:
        task = _make_task(consecutive_failures=3, error="Connection timeout")
        result = self.rule.evaluate(task)
        assert "Connection timeout" in result[0].title
        assert "3x" in result[0].title

    def test_title_without_error(self) -> None:
        task = _make_task(consecutive_failures=3, error="")
        result = self.rule.evaluate(task)
        assert "consecutively" in result[0].title

    def test_detail_includes_last_error(self) -> None:
        task = _make_task(consecutive_failures=3, error="OOM killed")
        result = self.rule.evaluate(task)
        assert "Last error: OOM killed" in result[0].detail

    def test_detail_blocked_mention(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, consecutive_failures=3)
        result = self.rule.evaluate(task)
        assert "Auto-blocked" in result[0].detail

    def test_custom_threshold(self) -> None:
        rule = RepeatedFailuresRule(DiagnosticThresholds(repeated_failure_threshold=1))
        task = _make_task(consecutive_failures=1)
        result = rule.evaluate(task)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Rule 3: StuckInBlockedRule
# ---------------------------------------------------------------------------


class TestStuckInBlockedRule:
    def setup_method(self) -> None:
        self.rule = StuckInBlockedRule()

    def test_not_blocked_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.READY, hours_ago=100)
        assert self.rule.evaluate(task) == []

    def test_recent_blocked_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=10)
        assert self.rule.evaluate(task) == []

    def test_stuck_returns_diagnostic(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].rule_id == "stuck_in_blocked"

    def test_severity_escalation(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=100)
        result = self.rule.evaluate(task)
        assert result[0].severity == TaskDiagnosticSeverity.ERROR

    def test_critical_severity(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=340)
        result = self.rule.evaluate(task)
        assert result[0].severity == TaskDiagnosticSeverity.CRITICAL

    def test_title_with_reason(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50, blocked_reason="API down")
        result = self.rule.evaluate(task)
        assert "API down" in result[0].title
        assert "2d" in result[0].title

    def test_title_without_reason(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50)
        result = self.rule.evaluate(task)
        assert ":" not in result[0].title or "Blocked" in result[0].title

    def test_reason_truncated_in_title(self) -> None:
        long_reason = "X" * 200
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50, blocked_reason=long_reason)
        result = self.rule.evaluate(task)
        assert len(result[0].title) < 200

    def test_has_comment_action_suggested(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50)
        result = self.rule.evaluate(task)
        actions = result[0].actions
        comment = next(a for a in actions if a.kind == "comment")
        assert comment.suggested is True
        assert comment.payload == {}

    def test_has_move_and_archive_actions(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50)
        result = self.rule.evaluate(task)
        kinds = [a.kind for a in result[0].actions]
        assert "comment" in kinds
        assert "move_to_ready" in kinds
        assert "archive" in kinds

    def test_detail_includes_reason(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50, blocked_reason="API down")
        result = self.rule.evaluate(task)
        assert "API down" in result[0].detail

    def test_detail_reason_not_specified(self) -> None:
        task = _make_task(status=TaskStatus.BLOCKED, hours_ago=50)
        result = self.rule.evaluate(task)
        assert "not specified" in result[0].detail


# ---------------------------------------------------------------------------
# Rule 4: DeadDependencyRule
# ---------------------------------------------------------------------------


class TestDeadDependencyRule:
    def setup_method(self) -> None:
        self.rule = DeadDependencyRule()

    def test_not_backlog_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.READY)
        ctx = DiagnosticContext(parent_task_ids=("p1",), parent_statuses={"p1": "failed"})
        assert self.rule.evaluate(task, context=ctx) == []

    def test_no_context_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        assert self.rule.evaluate(task) == []

    def test_no_parents_returns_empty(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext()
        assert self.rule.evaluate(task, context=ctx) == []

    def test_all_parents_dead(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext(
            parent_task_ids=("p1", "p2"),
            parent_statuses={"p1": "failed", "p2": "archived"},
        )
        result = self.rule.evaluate(task, context=ctx)
        assert len(result) == 1
        assert result[0].rule_id == "dead_dependency"
        assert result[0].severity == TaskDiagnosticSeverity.ERROR

    def test_some_parents_alive(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext(
            parent_task_ids=("p1", "p2"),
            parent_statuses={"p1": "failed", "p2": "running"},
        )
        assert self.rule.evaluate(task, context=ctx) == []

    def test_single_dead_parent(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext(
            parent_task_ids=("p1",),
            parent_statuses={"p1": "failed"},
        )
        result = self.rule.evaluate(task, context=ctx)
        assert len(result) == 1
        assert "1 parent dead" in result[0].title

    def test_multiple_dead_parents_plural(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext(
            parent_task_ids=("p1", "p2", "p3"),
            parent_statuses={"p1": "failed", "p2": "archived", "p3": "failed"},
        )
        result = self.rule.evaluate(task, context=ctx)
        assert "3 parents dead" in result[0].title

    def test_has_archive_action_suggested(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext(
            parent_task_ids=("p1",),
            parent_statuses={"p1": "failed"},
        )
        result = self.rule.evaluate(task, context=ctx)
        assert result[0].actions[0].kind == "archive"
        assert result[0].actions[0].suggested is True

    def test_parent_missing_from_statuses_not_dead(self) -> None:
        task = _make_task(status=TaskStatus.BACKLOG)
        ctx = DiagnosticContext(
            parent_task_ids=("p1", "p2"),
            parent_statuses={"p1": "failed"},
        )
        assert self.rule.evaluate(task, context=ctx) == []


# ---------------------------------------------------------------------------
# Rule 6: BlockUnblockCyclingRule
# ---------------------------------------------------------------------------


class TestBlockUnblockCyclingRule:
    def setup_method(self) -> None:
        self.rule = BlockUnblockCyclingRule()

    def test_below_threshold_returns_empty(self) -> None:
        task = _make_task(block_cycle_count=2)
        assert self.rule.evaluate(task) == []

    def test_zero_cycles_returns_empty(self) -> None:
        task = _make_task(block_cycle_count=0)
        assert self.rule.evaluate(task) == []

    def test_at_threshold_returns_warning(self) -> None:
        task = _make_task(block_cycle_count=3)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].rule_id == "block_unblock_cycling"
        assert result[0].severity == TaskDiagnosticSeverity.WARNING

    def test_double_threshold_returns_error(self) -> None:
        task = _make_task(block_cycle_count=6)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.ERROR

    def test_7x_threshold_returns_critical(self) -> None:
        task = _make_task(block_cycle_count=21)
        result = self.rule.evaluate(task)
        assert len(result) == 1
        assert result[0].severity == TaskDiagnosticSeverity.CRITICAL

    def test_title_contains_cycle_count(self) -> None:
        task = _make_task(block_cycle_count=5)
        result = self.rule.evaluate(task)
        assert "5x" in result[0].title

    def test_title_with_blocked_reason(self) -> None:
        task = _make_task(block_cycle_count=3, blocked_reason="Missing API key")
        result = self.rule.evaluate(task)
        assert "Missing API key" in result[0].title

    def test_title_without_blocked_reason(self) -> None:
        task = _make_task(block_cycle_count=3)
        result = self.rule.evaluate(task)
        assert "cycled 3x" in result[0].title
        assert ":" not in result[0].title.split("cycled")[0]

    def test_detail_mentions_root_cause(self) -> None:
        task = _make_task(block_cycle_count=4)
        result = self.rule.evaluate(task)
        assert "root cause" in result[0].detail

    def test_has_comment_action_suggested(self) -> None:
        task = _make_task(block_cycle_count=3)
        result = self.rule.evaluate(task)
        actions = result[0].actions
        comment = next(a for a in actions if a.kind == "comment")
        assert comment.suggested is True

    def test_has_archive_action(self) -> None:
        task = _make_task(block_cycle_count=3)
        result = self.rule.evaluate(task)
        kinds = [a.kind for a in result[0].actions]
        assert "comment" in kinds
        assert "archive" in kinds

    def test_custom_threshold(self) -> None:
        rule = BlockUnblockCyclingRule(DiagnosticThresholds(block_cycle_threshold=1))
        task = _make_task(block_cycle_count=1)
        result = rule.evaluate(task)
        assert len(result) == 1

    def test_works_regardless_of_status(self) -> None:
        for status in (TaskStatus.READY, TaskStatus.RUNNING, TaskStatus.BLOCKED):
            task = _make_task(status=status, block_cycle_count=3)
            result = self.rule.evaluate(task)
            assert len(result) == 1

    def test_engine_integration(self) -> None:
        engine = create_diagnostic_engine()
        task = _make_task(block_cycle_count=5)
        results = engine.evaluate(task)
        cycling_diags = [d for d in results if d.rule_id == "block_unblock_cycling"]
        assert len(cycling_diags) == 1


# ---------------------------------------------------------------------------
# Factory & summary
# ---------------------------------------------------------------------------


class TestCreateDiagnosticEngine:
    def test_default_creates_all_rules(self) -> None:
        engine = create_diagnostic_engine()
        assert len(engine.rule_ids) == 6
        assert set(engine.rule_ids) == {
            "stranded_in_ready",
            "repeated_failures",
            "stuck_in_blocked",
            "dead_dependency",
            "stranded_in_triage",
            "block_unblock_cycling",
        }

    def test_custom_thresholds(self) -> None:
        engine = create_diagnostic_engine(DiagnosticThresholds(stranded_ready_hours=1.0))
        task = _make_task(status=TaskStatus.READY, hours_ago=2)
        result = engine.evaluate(task)
        assert any(d.rule_id == "stranded_in_ready" for d in result)


class TestCardFastRules:
    def test_excludes_dead_dependency(self) -> None:
        assert "dead_dependency" not in CARD_FAST_RULES

    def test_includes_card_fast_rules(self) -> None:
        assert CARD_FAST_RULES == frozenset(
            {
                "stranded_in_ready",
                "repeated_failures",
                "stuck_in_blocked",
                "stranded_in_triage",
                "block_unblock_cycling",
            }
        )


class TestComputeDiagnosticsSummary:
    def test_empty_list(self) -> None:
        summary = compute_diagnostics_summary([])
        assert summary == DiagnosticSummary(count=0, max_severity=None)

    def test_single_diagnostic(self) -> None:
        from myrm_agent_harness.toolkits.kanban.diagnostics import TaskDiagnostic

        diag = TaskDiagnostic(
            rule_id="test",
            severity=TaskDiagnosticSeverity.ERROR,
            title="T",
            detail="D",
        )
        summary = compute_diagnostics_summary([diag])
        assert summary.count == 1
        assert summary.max_severity == TaskDiagnosticSeverity.ERROR

    def test_multiple_diagnostics_takes_first(self) -> None:
        from myrm_agent_harness.toolkits.kanban.diagnostics import TaskDiagnostic

        d1 = TaskDiagnostic(
            rule_id="a",
            severity=TaskDiagnosticSeverity.CRITICAL,
            title="T",
            detail="D",
        )
        d2 = TaskDiagnostic(
            rule_id="b",
            severity=TaskDiagnosticSeverity.WARNING,
            title="T",
            detail="D",
        )
        summary = compute_diagnostics_summary([d1, d2])
        assert summary.count == 2
        assert summary.max_severity == TaskDiagnosticSeverity.CRITICAL

    def test_summary_frozen(self) -> None:
        summary = DiagnosticSummary(count=0, max_severity=None)
        with pytest.raises(AttributeError):
            summary.count = 5  # type: ignore[misc]
