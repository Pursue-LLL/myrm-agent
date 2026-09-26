"""Unit tests for the nightly collaboration scorer (pure, no DB)."""

from __future__ import annotations

from app.services.skills.nightly_review.scorer import score_day


def _event(event_type: str, entity_id: str, entity_type: str = "agent") -> dict[str, object]:
    return {
        "event_type": event_type,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "summary": "x",
    }


def test_ignores_unknown_and_positive_types() -> None:
    events = [
        _event("evolution.approved", "a1"),
        _event("skill_growth.auto_applied", "s1", "skill"),
        _event("something.else", "a1"),
    ]
    assert score_day(events) == []


def test_clusters_approval_returns_above_threshold() -> None:
    events = [_event("review.rejected", "agent-a") for _ in range(3)]
    events.append(_event("review.rejected", "agent-b"))
    findings = score_day(events)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.entity_id == "agent-a"
    assert finding.category == "approval_return"
    assert finding.count == 3
    assert finding.recommendation == "review-reject-loop"


def test_tool_error_category_and_sort_order() -> None:
    events = [_event("evolution.apply_failed", "agent-z") for _ in range(4)]
    events.extend(_event("skill_growth.failed_scan", "skill-s", "skill") for _ in range(5))
    findings = score_day(events)
    assert [finding.entity_id for finding in findings] == ["skill-s", "agent-z"]
    assert all(finding.category == "tool_error" for finding in findings)
    assert all(finding.recommendation == "tool-error-cluster" for finding in findings)


def test_custom_threshold() -> None:
    events = [_event("review.rejected", "agent-a") for _ in range(2)]
    assert score_day(events) == []
    assert len(score_day(events, min_count=2)) == 1
