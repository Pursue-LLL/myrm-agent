"""Unit tests for post-import readiness contract assembly."""

from __future__ import annotations

from app.services.memory.operations.crud.import_readiness import build_import_readiness


def test_build_import_readiness_ready_without_issues() -> None:
    readiness = build_import_readiness(
        providers_configured=True,
        source_has_api_keys=False,
        diagnostic_status="ready",
        diagnostic_failed_count=0,
        mcp_config_count=0,
        workspace_rules_skipped=0,
    )

    assert readiness.status == "ready"
    assert readiness.issues == []


def test_build_import_readiness_warning_collects_non_blocking_issues() -> None:
    readiness = build_import_readiness(
        providers_configured=True,
        source_has_api_keys=False,
        diagnostic_status="warning",
        diagnostic_failed_count=2,
        mcp_config_count=3,
        workspace_rules_skipped=1,
    )

    assert readiness.status == "warning"
    issue_codes = {issue.code for issue in readiness.issues}
    assert issue_codes == {
        "post_import_diagnostics_warning",
        "mcp_servers_imported_disabled",
        "workspace_rules_skipped",
    }


def test_build_import_readiness_critical_on_provider_gap() -> None:
    readiness = build_import_readiness(
        providers_configured=False,
        source_has_api_keys=True,
        diagnostic_status="ready",
        diagnostic_failed_count=0,
        mcp_config_count=0,
        workspace_rules_skipped=0,
    )

    assert readiness.status == "critical"
    assert [issue.code for issue in readiness.issues] == ["providers_not_configured"]


def test_build_import_readiness_does_not_block_without_api_keys() -> None:
    readiness = build_import_readiness(
        providers_configured=False,
        source_has_api_keys=False,
        diagnostic_status="ready",
        diagnostic_failed_count=0,
        mcp_config_count=0,
        workspace_rules_skipped=0,
    )

    assert readiness.status == "ready"
    assert readiness.issues == []


def test_resolve_readiness_issue_action_maps_known_codes() -> None:
    from app.services.memory.operations.crud.import_readiness import resolve_readiness_issue_action

    action = resolve_readiness_issue_action("mcp_servers_imported_disabled")
    assert action is not None
    assert action.settings_path == "/settings/mcp"


def test_pick_primary_readiness_issue_prefers_critical() -> None:
    from app.schemas.memory.archive import MemoryImportReadinessIssue
    from app.services.memory.operations.crud.import_readiness import pick_primary_readiness_issue

    issues = [
        MemoryImportReadinessIssue(code="workspace_rules_skipped", severity="warning", params={"count": 1}),
        MemoryImportReadinessIssue(code="providers_not_configured", severity="critical"),
    ]
    primary = pick_primary_readiness_issue(issues)
    assert primary is not None
    assert primary.code == "providers_not_configured"
