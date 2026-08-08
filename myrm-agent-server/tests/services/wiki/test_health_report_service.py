"""Unit tests for wiki health report helpers."""

from __future__ import annotations

import pytest
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


def test_persist_wiki_health_snapshot_writes_vault_report(tmp_path) -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.services.wiki.health_report_service import persist_wiki_health_snapshot

    structure = WikiStructure(base_dir=tmp_path)
    structure.ensure_structure()
    report = report_from_lint_issues(mode="full", issues=[])
    persist_wiki_health_snapshot(structure, report)
    snapshot_path = structure.wiki_dir / "reports" / "last-health.json"
    assert snapshot_path.is_file()
    assert '"mode": "full"' in snapshot_path.read_text(encoding="utf-8")


def test_load_wiki_health_snapshot_missing_returns_none(tmp_path) -> None:
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.services.wiki.health_report_service import load_wiki_health_snapshot

    structure = WikiStructure(base_dir=tmp_path)
    structure.ensure_structure()
    assert load_wiki_health_snapshot(structure) is None


def test_merge_drift_from_snapshot_dedupes_by_location() -> None:
    from app.services.wiki.health_report_service import (
        WikiHealthIssueResponse,
        WikiHealthReportResponse,
        _merge_drift_from_snapshot,
    )

    structural = [
        LintIssue(
            issue_type="broken_link",
            severity="medium",
            location="notes/alpha.md",
            description="Broken",
            action_kind="navigate",
        ),
    ]
    snapshot = WikiHealthReportResponse(
        mode="full",
        generated_at="2026-08-06T00:00:00+00:00",
        open_actions_count=2,
        issues_found=2,
        drift_sampled=True,
        issues=[
            WikiHealthIssueResponse(
                issue_type="drift",
                severity="medium",
                location="notes/beta.md",
                description="Possible drift",
                action_kind="navigate",
            ),
            WikiHealthIssueResponse(
                issue_type="drift",
                severity="medium",
                location="notes/alpha.md",
                description="Duplicate drift",
                action_kind="navigate",
            ),
        ],
    )

    merged, drift_sampled = _merge_drift_from_snapshot(structural, snapshot)
    assert drift_sampled is True
    assert [item.location for item in merged] == ["notes/alpha.md", "notes/beta.md"]
    assert merged[1].issue_type == "drift"


@pytest.mark.asyncio
async def test_build_wiki_health_report_merges_snapshot_drift(tmp_path) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

    from app.services.wiki.health_report_service import (
        WikiHealthIssueResponse,
        WikiHealthReportResponse,
        build_wiki_health_report,
        persist_wiki_health_snapshot,
    )

    structure = WikiStructure(base_dir=tmp_path)
    structure.ensure_structure()
    persist_wiki_health_snapshot(
        structure,
        WikiHealthReportResponse(
            mode="full",
            generated_at="2026-08-06T00:00:00+00:00",
            open_actions_count=1,
            issues_found=1,
            drift_sampled=True,
            issues=[
                WikiHealthIssueResponse(
                    issue_type="drift",
                    severity="medium",
                    location="notes/beta.md",
                    description="Possible drift",
                    action_kind="navigate",
                ),
            ],
        ),
    )

    linter = MagicMock()
    linter.scan = AsyncMock(
        return_value=(
            [
                LintIssue(
                    issue_type="broken_link",
                    severity="medium",
                    location="notes/alpha.md",
                    description="Broken",
                    action_kind="navigate",
                ),
            ],
            {},
        ),
    )

    report = await build_wiki_health_report(linter=linter, structure=structure)
    assert report.mode == "structural"
    assert report.drift_sampled is True
    assert report.drift_checked_at == "2026-08-06T00:00:00+00:00"
    assert report.issues_found == 2
    assert {item.issue_type for item in report.issues} == {"broken_link", "drift"}
    linter.scan.assert_awaited_once()


class _NoopLlm:
    async def ainvoke(self, _messages: list[object]) -> object:
        class _Resp:
            content = "NO_DRIFT"

        return _Resp()


@pytest.mark.asyncio
async def test_build_wiki_health_report_includes_provenance_gap(tmp_path) -> None:
    from myrm_agent_harness.toolkits.wiki.core.config import WikiConfig
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.maintenance.linter import WikiLinter
    from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode

    from app.services.wiki.health_report_service import build_wiki_health_report

    structure = WikiStructure(base_dir=tmp_path / "vault")
    structure.ensure_structure()
    concept = structure.concepts_dir / "policy.md"
    concept.write_text(
        "---\ntitle: Policy\ntype: concept\nprovenance: compiled\n---\n\nBody",
        encoding="utf-8",
    )

    linter = WikiLinter(_NoopLlm(), structure, WikiConfig())
    scan_issues, _raw_scan = await linter.scan(
        MaintainMode.STRUCTURAL,
        include_raw_security=False,
    )
    assert any(issue.issue_type == "provenance_gap" for issue in scan_issues)

    report = await build_wiki_health_report(linter=linter, structure=structure)
    provenance_issues = [
        item for item in report.issues if item.issue_type == "provenance_gap"
    ]
    assert provenance_issues
    assert report.open_actions_count >= 1
    assert provenance_issues[0].action_kind == "navigate"
