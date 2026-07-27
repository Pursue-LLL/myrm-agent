"""Memory import readiness contract builder.

[INPUT]
app.schemas.memory.archive::MemoryImportReadiness (POS: 记忆归档与导入共享 Schema。api 与 services 层共用。)
app.schemas.memory.archive::MemoryImportReadinessIssue (POS: 记忆归档与导入共享 Schema。api 与 services 层共用。)

[OUTPUT]
build_import_readiness: aggregate post-import facts into a readiness contract (status + issue codes).

[POS]
记忆导入就绪合同构建层。负责把 provider、diagnostic、MCP 与规则跳过事实归并为可执行门禁状态。
"""

from __future__ import annotations

from app.schemas.memory.archive import MemoryImportReadiness, MemoryImportReadinessIssue


def build_import_readiness(
    *,
    providers_configured: bool | None,
    source_has_api_keys: bool,
    diagnostic_status: str | None,
    diagnostic_failed_count: int,
    mcp_config_count: int,
    workspace_rules_skipped: int,
) -> MemoryImportReadiness:
    issues: list[MemoryImportReadinessIssue] = []

    if providers_configured is False and source_has_api_keys:
        issues.append(
            MemoryImportReadinessIssue(
                code="providers_not_configured",
                severity="critical",
            )
        )

    if diagnostic_status in {"critical", "failed"}:
        issues.append(
            MemoryImportReadinessIssue(
                code="post_import_diagnostics_critical",
                severity="critical",
                params={"failed_count": max(1, diagnostic_failed_count)},
            )
        )
    elif diagnostic_status in {"warning", "missing"}:
        issues.append(
            MemoryImportReadinessIssue(
                code="post_import_diagnostics_warning",
                severity="warning",
                params={"failed_count": diagnostic_failed_count},
            )
        )

    if mcp_config_count > 0:
        issues.append(
            MemoryImportReadinessIssue(
                code="mcp_servers_imported_disabled",
                severity="warning",
                params={"count": mcp_config_count},
            )
        )

    if workspace_rules_skipped > 0:
        issues.append(
            MemoryImportReadinessIssue(
                code="workspace_rules_skipped",
                severity="warning",
                params={"count": workspace_rules_skipped},
            )
        )

    if any(issue.severity == "critical" for issue in issues):
        status = "critical"
    elif issues:
        status = "warning"
    else:
        status = "ready"
    return MemoryImportReadiness(status=status, issues=issues)
