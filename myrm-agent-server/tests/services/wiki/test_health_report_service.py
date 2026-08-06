"""Unit tests for wiki health report helpers."""

from __future__ import annotations

from myrm_agent_harness.toolkits.wiki.core.types import LintIssue
from myrm_agent_harness.toolkits.wiki.maintenance.issue_kind import count_open_actions

from app.services.wiki.health_report_service import report_from_lint_issues


def test_count_open_actions_excludes_informational() -> None:
    issues = [
        LintIssue(
            issue_type="broken_link",
            severity="medium",
            location="concepts/a.md",
            description="Broken",
            action_kind="navigate",
        ),
        LintIssue(
            issue_type="security_redacted",
            severity="medium",
            location="raw/x.md",
            description="Redacted",
            action_kind="info",
        ),
    ]
    assert count_open_actions(issues) == 1


def test_report_from_lint_issues_maps_open_actions() -> None:
    issues = [
        LintIssue(
            issue_type="stale",
            severity="medium",
            location="raw/note.md",
            description="Stale raw",
            action_kind="recompile",
        ),
    ]
    report = report_from_lint_issues(mode="structural", issues=issues)
    assert report.open_actions_count == 1
    assert report.issues_found == 1
    assert report.issues[0].issue_type == "stale"
    assert report.issues[0].action_kind == "recompile"
