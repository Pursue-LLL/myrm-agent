"""Wiki health report orchestration for REST surfaces.

[INPUT]
- myrm_agent_harness.toolkits.wiki.maintenance.linter::WikiLinter (POS: scan engine)
- myrm_agent_harness.toolkits.wiki.maintenance.issue_kind::count_open_actions (POS: open action metric)
- app.services.wiki.vault::get_wiki_archiver (POS: archiver accessor)

[OUTPUT]
- build_wiki_health_report: structural scan + optional vault drift merge for GET /wiki/health-report
- load_wiki_health_snapshot: read vault reports/last-health.json
- persist_wiki_health_snapshot: vault JSON SSOT after maintain

[POS]
Server-only health report orchestration. Zero LLM on structural GET; snapshots written after maintain.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.core.types import LintIssue
from myrm_agent_harness.toolkits.wiki.maintenance.issue_kind import count_open_actions
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

WikiHealthReportMode = Literal["structural", "full"]
_HEALTH_REPORT_FILENAME = "last-health.json"
_MAX_PERSISTED_ISSUES = 200


class WikiHealthIssueResponse(BaseModel):
    issue_type: str
    severity: str
    location: str
    description: str
    action_kind: str
    suggested_fix: str | None = None


class WikiHealthReportResponse(BaseModel):
    mode: WikiHealthReportMode
    generated_at: str
    open_actions_count: int
    issues_found: int
    issues: list[WikiHealthIssueResponse] = Field(default_factory=list)
    drift_sampled: bool = False
    drift_checked_at: str | None = None
    duplicate_groups_pending: int = 0
    synthesis_pending: int = 0


def _health_report_path(structure: WikiStructure) -> Path:
    reports_dir = structure.wiki_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    return reports_dir / _HEALTH_REPORT_FILENAME


def _issue_to_response(issue: LintIssue) -> WikiHealthIssueResponse:
    return WikiHealthIssueResponse(
        issue_type=issue.issue_type,
        severity=issue.severity,
        location=issue.location,
        description=issue.description,
        action_kind=issue.action_kind,
        suggested_fix=issue.suggested_fix,
    )


def _cap_issues(issues: list[LintIssue]) -> list[LintIssue]:
    if len(issues) <= _MAX_PERSISTED_ISSUES:
        return issues
    return issues[:_MAX_PERSISTED_ISSUES]


def _response_to_lint_issue(item: WikiHealthIssueResponse) -> LintIssue:
    return LintIssue(
        issue_type=item.issue_type,
        severity=item.severity,
        location=item.location,
        description=item.description,
        action_kind=item.action_kind,
        suggested_fix=item.suggested_fix,
    )


def load_wiki_health_snapshot(
    structure: WikiStructure,
) -> WikiHealthReportResponse | None:
    """Load the latest maintain health snapshot from the vault, if present."""
    path = _health_report_path(structure)
    if not path.is_file():
        return None
    try:
        return WikiHealthReportResponse.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        logger.warning("Failed to load wiki health snapshot from %s: %s", path, exc)
        return None


def _merge_drift_from_snapshot(
    structural_issues: list[LintIssue],
    snapshot: WikiHealthReportResponse,
) -> tuple[list[LintIssue], bool]:
    """Append persisted full-maintain drift samples not already present in structural scan."""
    if snapshot.mode != "full":
        return structural_issues, False

    existing_locations = {item.location for item in structural_issues}
    merged = list(structural_issues)
    for item in snapshot.issues:
        if item.issue_type != "drift":
            continue
        if item.location in existing_locations:
            continue
        merged.append(_response_to_lint_issue(item))
        existing_locations.add(item.location)

    return merged, any(item.issue_type == "drift" for item in merged)


def _drift_checked_at(
    *,
    drift_sampled: bool,
    snapshot: WikiHealthReportResponse | None,
    fallback_at: str | None = None,
) -> str | None:
    if not drift_sampled:
        return None
    if snapshot is not None and snapshot.mode == "full":
        return snapshot.generated_at
    return fallback_at


async def build_wiki_health_report(
    *,
    linter: object,
    structure: WikiStructure,
    mode: WikiHealthReportMode = "structural",
    duplicate_groups_pending: int = 0,
    synthesis_pending: int = 0,
) -> WikiHealthReportResponse:
    """Build a read-only health report for GET /wiki/health-report.

    Always runs a zero-LLM structural scan. When a full-maintain snapshot exists in the
    vault, drift samples from that snapshot are merged in so refresh preserves them.
    """
    del mode  # GET remains structural; full-mode drift comes from vault snapshot merge.
    issues, _raw_scan = await linter.scan(  # type: ignore[attr-defined]
        MaintainMode.STRUCTURAL,
        include_raw_security=False,
    )
    drift_sampled = False
    snapshot = load_wiki_health_snapshot(structure)
    if snapshot is not None:
        issues, drift_sampled = _merge_drift_from_snapshot(issues, snapshot)

    capped = _cap_issues(issues)
    open_count = count_open_actions(capped)
    generated_at = datetime.now(UTC).isoformat()
    return WikiHealthReportResponse(
        mode="structural",
        generated_at=generated_at,
        open_actions_count=open_count,
        issues_found=len(issues),
        issues=[_issue_to_response(item) for item in capped],
        drift_sampled=drift_sampled,
        drift_checked_at=_drift_checked_at(
            drift_sampled=drift_sampled,
            snapshot=snapshot,
        ),
        duplicate_groups_pending=duplicate_groups_pending,
        synthesis_pending=synthesis_pending,
    )


def persist_wiki_health_snapshot(
    structure: WikiStructure,
    report: WikiHealthReportResponse,
) -> None:
    """Write the latest health report JSON into the wiki vault."""
    path = _health_report_path(structure)
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")


def report_from_lint_issues(
    *,
    mode: WikiHealthReportMode,
    issues: list[LintIssue],
    duplicate_groups_pending: int = 0,
    synthesis_pending: int = 0,
) -> WikiHealthReportResponse:
    """Build a health report DTO from an in-memory lint issue list."""
    capped = _cap_issues(issues)
    generated_at = datetime.now(UTC).isoformat()
    drift_sampled = mode == "full" and any(
        item.issue_type == "drift" for item in issues
    )
    return WikiHealthReportResponse(
        mode=mode,
        generated_at=generated_at,
        open_actions_count=count_open_actions(capped),
        issues_found=len(issues),
        issues=[_issue_to_response(item) for item in capped],
        drift_sampled=drift_sampled,
        drift_checked_at=_drift_checked_at(
            drift_sampled=drift_sampled,
            snapshot=None,
            fallback_at=generated_at if drift_sampled else None,
        ),
        duplicate_groups_pending=duplicate_groups_pending,
        synthesis_pending=synthesis_pending,
    )
