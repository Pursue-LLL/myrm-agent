"""Memory import readiness contract builder.

[INPUT]
app.schemas.memory.archive::MemoryImportReadiness (POS: 记忆归档与导入共享 Schema。api 与 services 层共用。)
app.schemas.memory.archive::MemoryImportReadinessIssue (POS: 记忆归档与导入共享 Schema。api 与 services 层共用。)

[OUTPUT]
build_readiness_issue: build issue with settings_path populated.
build_import_readiness: aggregate post-import facts into a readiness contract (status + issue codes).
resolve_readiness_issue_action / pick_primary_readiness_issue / resolve_migration_readiness_gap_message: issue SSOT for stream preflight and settings deep links.

[POS]
记忆导入就绪合同构建层。负责把 provider、diagnostic、MCP 与规则跳过事实归并为可执行门禁状态。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.schemas.memory.archive import MemoryImportReadiness, MemoryImportReadinessIssue

ImportReadinessStatus = Literal["ready", "warning", "critical"]


@dataclass(frozen=True, slots=True)
class ReadinessIssueAction:
    """Server-side settings route for a post-import readiness issue code."""

    settings_path: str


_READINESS_ISSUE_ACTIONS: dict[str, ReadinessIssueAction] = {
    "providers_not_configured": ReadinessIssueAction(settings_path="/settings/models"),
    "post_import_diagnostics_critical": ReadinessIssueAction(
        settings_path="/settings/memory"
    ),
    "post_import_diagnostics_warning": ReadinessIssueAction(
        settings_path="/settings/memory"
    ),
    "mcp_servers_imported_disabled": ReadinessIssueAction(
        settings_path="/settings/mcp"
    ),
    "workspace_rules_skipped": ReadinessIssueAction(
        settings_path="/settings/memory?sub=migration"
    ),
}


def resolve_readiness_issue_action(code: str) -> ReadinessIssueAction | None:
    normalized = code.strip()
    if not normalized:
        return None
    return _READINESS_ISSUE_ACTIONS.get(normalized)


def build_readiness_issue(
    *,
    code: str,
    severity: Literal["warning", "critical"],
    params: dict[str, str | int | float | bool] | None = None,
) -> MemoryImportReadinessIssue:
    """Build a readiness issue with server-side settings_path populated."""

    action = resolve_readiness_issue_action(code)
    return MemoryImportReadinessIssue(
        code=code,
        severity=severity,
        params=params or {},
        settings_path=action.settings_path if action is not None else None,
    )


def pick_primary_readiness_issue(
    issues: list[MemoryImportReadinessIssue],
) -> MemoryImportReadinessIssue | None:
    for severity in ("critical", "warning"):
        for issue in issues:
            if issue.severity == severity:
                return issue
    return issues[0] if issues else None


def resolve_migration_readiness_gap_message(
    *,
    status: ImportReadinessStatus,
    issue_code: str | None,
    locale: str | None,
) -> str:
    is_zh = bool(locale and locale.lower().startswith("zh"))
    if issue_code == "providers_not_configured":
        return (
            "迁移助手尚未就绪，请先在设置中配置模型提供商后再继续对话。"
            if is_zh
            else "This migrated assistant is not ready to chat yet. Configure model providers in Settings before continuing."
        )
    if issue_code == "mcp_servers_imported_disabled":
        return (
            "迁移助手已导入 MCP 服务但尚未启用，请前往 MCP 设置启用后再继续。"
            if is_zh
            else "MCP servers were imported but are not enabled yet. Open MCP Settings to enable them."
        )
    if issue_code in {
        "post_import_diagnostics_critical",
        "post_import_diagnostics_warning",
    }:
        return (
            "迁移后记忆诊断仍有问题，请前往记忆中心查看详情。"
            if is_zh
            else "Post-import memory diagnostics still need attention. Open Memory Center for details."
        )
    if issue_code == "workspace_rules_skipped":
        return (
            "部分工作区规则未写入，请前往迁移设置复查。"
            if is_zh
            else "Some workspace rules were skipped during migration. Review migration settings."
        )
    if status == "critical":
        return (
            "迁移助手尚未就绪，请先完成设置中的必要配置。"
            if is_zh
            else "This migrated assistant is not ready to chat yet. Complete required Settings first."
        )
    return (
        "迁移助手可以聊天，但仍有待完成项，建议先查看设置。"
        if is_zh
        else "This migrated assistant can chat, but migration follow-ups remain in Settings."
    )


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
            build_readiness_issue(
                code="providers_not_configured",
                severity="critical",
            )
        )

    if diagnostic_status in {"critical", "failed"}:
        issues.append(
            build_readiness_issue(
                code="post_import_diagnostics_critical",
                severity="critical",
                params={"failed_count": max(1, diagnostic_failed_count)},
            )
        )
    elif diagnostic_status in {"warning", "missing"}:
        issues.append(
            build_readiness_issue(
                code="post_import_diagnostics_warning",
                severity="warning",
                params={"failed_count": diagnostic_failed_count},
            )
        )

    if mcp_config_count > 0:
        issues.append(
            build_readiness_issue(
                code="mcp_servers_imported_disabled",
                severity="warning",
                params={"count": mcp_config_count},
            )
        )

    if workspace_rules_skipped > 0:
        issues.append(
            build_readiness_issue(
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
