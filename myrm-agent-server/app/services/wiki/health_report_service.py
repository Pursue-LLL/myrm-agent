"""Wiki health report orchestration for REST surfaces.

[INPUT]
- myrm_agent_harness.toolkits.wiki.maintenance.linter::WikiLinter (POS: scan engine)
- myrm_agent_harness.toolkits.wiki.maintenance.issue_kind::count_open_actions (POS: open action metric)
- app.services.wiki.vault_service::get_wiki_archiver (POS: archiver accessor)

[OUTPUT]
- build_wiki_health_report: structural scan snapshot for GET /wiki/health-report
- persist_wiki_health_snapshot / load_wiki_health_snapshot: vault JSON SSOT

[POS]
Server-only health report orchestration. Zero LLM on structural GET; snapshots written after maintain.
"""

from __future__ import annotations

import json
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


async def build_wiki_health_report(
    *,
    linter: object,
    structure: WikiStructure,
    mode: WikiHealthReportMode = "structural",
    duplicate_groups_pending: int = 0,
    synthesis_pending: int = 0,
) -> WikiHealthReportResponse:
    """Build a read-only health report (structural mode avoids raw security mutation)."""
    maintain_mode = MaintainMode.FULL if mode == "full" else MaintainMode.STRUCTURAL
    include_raw_security = mode == "full"
    issues, _raw_scan = await linter.scan(  # type: ignore[attr-defined]
        maintain_mode,
        include_raw_security=include_raw_security,
    )
    capped = _cap_issues(issues)
    open_count = count_open_actions(capped)
    return WikiHealthReportResponse(
        mode=mode,
        generated_at=datetime.now(UTC).isoformat(),
        open_actions_count=open_count,
        issues_found=len(issues),
        issues=[_issue_to_response(item) for item in capped],
        drift_sampled=mode == "full",
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


def load_wiki_health_snapshot(structure: WikiStructure) -> WikiHealthReportResponse | None:
    """Load persisted health report from vault when present."""
    path = _health_report_path(structure)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return WikiHealthReportResponse.model_validate(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Invalid wiki health snapshot at %s: %s", path, exc)
        return None


def report_from_lint_issues(
    *,
    mode: WikiHealthReportMode,
    issues: list[LintIssue],
    duplicate_groups_pending: int = 0,
    synthesis_pending: int = 0,
) -> WikiHealthReportResponse:
    """Build a health report DTO from an in-memory lint issue list."""
    capped = _cap_issues(issues)
    return WikiHealthReportResponse(
        mode=mode,
        generated_at=datetime.now(UTC).isoformat(),
        open_actions_count=count_open_actions(capped),
        issues_found=len(issues),
        issues=[_issue_to_response(item) for item in capped],
        drift_sampled=mode == "full",
        duplicate_groups_pending=duplicate_groups_pending,
        synthesis_pending=synthesis_pending,
    )
