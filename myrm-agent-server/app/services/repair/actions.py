"""White-listed runtime repair actions.

[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: framework health report)
- myrm_agent_harness.toolkits.browser::* (POS: browser orphan process maintenance)
- app.services.repair.models::RepairActionId, RepairRiskLevel, RepairScope, RepairAction, RepairActionExecuteRequest, RepairActionExecuteResult (POS: 修复动作数据契约与模型定义)
- app.services.repair.sqlite_repair::build_sqlite_backup_action, execute_sqlite_backup, execute_sqlite_restore (POS: SQLite 热备份与还原自愈动作具体执行逻辑)
- app.core.infra.health.session_diagnostics::count_orphan_empty_sessions, purge_orphan_empty_sessions (POS: 孤儿会话统计与物理清理)

[OUTPUT]
- RepairAction: GUI-safe repair action contract
- build_repair_actions: derive repair actions from current health signals
- execute_repair_action: run a white-listed repair action

[POS]
Server business layer repair contract. Agents may surface these actions to the
user, but only this service executes the white-listed implementation after an
explicit user decision.
"""

from __future__ import annotations

import asyncio

from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from .models import (
    RepairAction,
    RepairActionExecuteRequest,
    RepairActionExecuteResult,
    RepairActionId,
    RepairRiskLevel,
    RepairScope,
)
from .sqlite_repair import (
    build_sqlite_backup_action as _sqlite_backup_action,
)
from .sqlite_repair import (
    execute_sqlite_backup as _execute_sqlite_backup,
)
from .sqlite_repair import (
    execute_sqlite_restore as _execute_sqlite_restore,
)
from .sqlite_repair import (
    get_sqlite_backup_manager as _get_sqlite_backup_manager,
)

__all__ = [
    "RepairAction",
    "RepairActionExecuteRequest",
    "RepairActionExecuteResult",
    "RepairActionId",
    "RepairRiskLevel",
    "RepairScope",
    "build_repair_actions",
    "execute_repair_action",
]


def _action_key(action: RepairAction) -> tuple[str, str]:
    return (action.action_id.value, action.component)


def _dedupe(actions: list[RepairAction]) -> list[RepairAction]:
    seen: set[tuple[str, str]] = set()
    unique_actions: list[RepairAction] = []
    for action in actions:
        key = _action_key(action)
        if key in seen:
            continue
        seen.add(key)
        unique_actions.append(action)
    return unique_actions


def _action_for_report(report: HealthReport, layer: str) -> RepairAction | None:
    status = report.status.lower()
    if status not in {"warn", "fail"}:
        return None

    reason = report.detail or report.message

    if report.component_name in {"WorkspaceStorage", "Database"}:
        return RepairAction(
            action_id=RepairActionId.REVIEW_WORKSPACE_STORAGE,
            title="Review workspace storage",
            description="Workspace or SQLite storage is unhealthy and may block file writes, memory, or skill persistence.",
            component=report.component_name,
            layer=layer,
            scope=RepairScope.CURRENT_WORKSPACE,
            risk_level=RepairRiskLevel.MEDIUM,
            executable=False,
            method=None,
            endpoint=None,
            reason=reason,
            expected_effect="Guide the user to fix disk, permission, or volume mount issues before continuing.",
            does_not_do=[
                "Does not modify database files.",
                "Does not delete workspace content.",
            ],
        )

    if report.component_name in {
        "Network",
        "VectorDB",
        "SystemResources",
        "AgentEngine",
    }:
        return RepairAction(
            action_id=RepairActionId.REVIEW_RUNTIME_DEPENDENCY,
            title=f"Review {report.component_name} runtime issue",
            description="A runtime dependency needs user or operator attention before reliable agent execution can continue.",
            component=report.component_name,
            layer=layer,
            scope=RepairScope.CURRENT_RUNTIME,
            risk_level=RepairRiskLevel.LOW,
            executable=False,
            method=None,
            endpoint=None,
            reason=reason,
            expected_effect="Make the root cause visible in the GUI with the original diagnostic suggestion.",
            does_not_do=[
                "Does not run shell commands.",
                "Does not change configuration automatically.",
            ],
        )

    return None


async def _browser_orphan_action() -> RepairAction | None:
    try:
        from myrm_agent_harness.toolkits.browser import find_orphan_automation_processes
    except ImportError:
        return None

    orphans = await asyncio.to_thread(find_orphan_automation_processes)
    if not orphans:
        return None

    return RepairAction(
        action_id=RepairActionId.CLEANUP_BROWSER_ORPHANS,
        title="Clean up orphan browser processes",
        description=f"Found {len(orphans)} orphan browser automation process(es) that may slow down local or sandbox execution.",
        component="BrowserRuntime",
        layer="server",
        scope=RepairScope.CURRENT_RUNTIME,
        risk_level=RepairRiskLevel.MEDIUM,
        executable=True,
        method="POST",
        endpoint=f"/health/repair-actions/{RepairActionId.CLEANUP_BROWSER_ORPHANS.value}/execute",
        reason="Browser automation processes outlived their agent session.",
        expected_effect="Terminates only detected automation browser orphan processes.",
        does_not_do=[
            "Does not close normal user browser windows.",
            "Does not delete browser profiles or workspace files.",
        ],
    )


def _dlq_action(server_reports: list[dict[str, object]]) -> RepairAction | None:
    for report in server_reports:
        # server_reports can be a list of dicts or a list of HealthReport objects
        if isinstance(report, dict):
            comp_name = report.get("component_name")
            status = report.get("status")
            msg = str(report.get("message", "DLQ reported failed messages."))
        else:
            comp_name = getattr(report, "component_name", None)
            status = getattr(report, "status", None)
            msg = getattr(report, "message", "DLQ reported failed messages.")

        if comp_name == "DLQ" and status in {"warn", "fail"}:
            return RepairAction(
                action_id=RepairActionId.REVIEW_CHANNEL_DLQ,
                title="Review failed channel messages",
                description="The channel dead-letter queue contains failed messages that need inspection before retry.",
                component="DLQ",
                layer="server",
                scope=RepairScope.INTEGRATION,
                risk_level=RepairRiskLevel.LOW,
                executable=False,
                method=None,
                endpoint=None,
                reason=msg,
                expected_effect="Show operators why channel delivery is degraded and prevent silent task failure.",
                does_not_do=["Does not retry or delete failed messages automatically."],
            )
    return None


def _orphan_session_action(server_reports: list[dict[str, object]]) -> RepairAction | None:
    for report in server_reports:
        comp_name = report.get("component_name") if isinstance(report, dict) else getattr(report, "component_name", None)
        meta = report.get("meta_data") if isinstance(report, dict) else getattr(report, "meta_data", None)
        msg = str(
            report.get("message", "Orphan blank sessions detected.")
            if isinstance(report, dict)
            else getattr(report, "message", "Orphan blank sessions detected.")
        )

        orphan_count = 0
        if isinstance(meta, dict):
            orphan_count = int(meta.get("orphan_session_count", 0))

        if comp_name == "OrphanSession" and orphan_count > 0:
            return RepairAction(
                action_id=RepairActionId.PURGE_ORPHAN_SESSIONS,
                title="Purge orphan blank sessions",
                description="Permanently purge legacy empty sessions with zero assistant responses, releasing database rows, search indices, and sandbox volumes.",
                component="OrphanSession",
                layer="server",
                scope=RepairScope.CURRENT_WORKSPACE,
                risk_level=RepairRiskLevel.MEDIUM,
                requires_approval=True,
                executable=True,
                method="POST",
                endpoint=f"/health/repair-actions/{RepairActionId.PURGE_ORPHAN_SESSIONS.value}/execute",
                reason=msg,
                expected_effect="Permanently removes orphan session DB records, FTS5 indices, checkpointer data, and workspace sandbox directories.",
                does_not_do=[
                    "Does not delete active sessions or sessions with any assistant messages.",
                    "Does not purge sessions created within the 15-minute grace window.",
                ],
            )
    return None


async def build_repair_actions(
    harness_reports: list[HealthReport], server_reports: list[dict[str, object]]
) -> list[RepairAction]:
    """Build safe repair recommendations from current health signals."""

    actions: list[RepairAction] = []
    for report in harness_reports:
        action = _action_for_report(report, layer="harness")
        if action is not None:
            actions.append(action)

    dlq_action = _dlq_action(server_reports)
    if dlq_action is not None:
        actions.append(dlq_action)

    orphan_action = _orphan_session_action(server_reports)
    if orphan_action is not None:
        actions.append(orphan_action)

    browser_action = await _browser_orphan_action()
    if browser_action is not None:
        actions.append(browser_action)

    sqlite_action = _sqlite_backup_action()
    if sqlite_action is not None:
        actions.append(sqlite_action)

    return _dedupe(actions)


async def execute_repair_action(action_id: RepairActionId, request: RepairActionExecuteRequest) -> RepairActionExecuteResult:
    """Execute a white-listed repair action."""

    if action_id == RepairActionId.SQLITE_BACKUP_NOW:
        return _execute_sqlite_backup(request, manager_getter=_get_sqlite_backup_manager)

    if action_id == RepairActionId.SQLITE_RESTORE_LATEST:
        return _execute_sqlite_restore(request, manager_getter=_get_sqlite_backup_manager)

    if action_id == RepairActionId.PURGE_ORPHAN_SESSIONS:
        from app.core.infra.health.session_diagnostics import (
            count_orphan_empty_sessions,
            purge_orphan_empty_sessions,
        )

        if not request.dry_run and not request.confirm:
            return RepairActionExecuteResult(
                action_id=action_id,
                status="confirmation_required",
                changed=False,
                dry_run=False,
                message="Purging orphan sessions permanently deletes database rows and sandbox directories. Confirm required.",
            )

        if request.dry_run:
            orphan_count = await count_orphan_empty_sessions(older_than_minutes=15)
            return RepairActionExecuteResult(
                action_id=action_id,
                status="dry_run",
                changed=False,
                dry_run=True,
                message=f"Dry run: {orphan_count} orphan session(s) would be permanently purged.",
                details={"orphan_count": orphan_count},
            )

        deleted_count = await purge_orphan_empty_sessions(older_than_minutes=15)
        return RepairActionExecuteResult(
            action_id=action_id,
            status="completed",
            changed=deleted_count > 0,
            dry_run=False,
            message=f"Permanently purged {deleted_count} orphan session(s).",
            details={"deleted_count": deleted_count},
        )

    if action_id != RepairActionId.CLEANUP_BROWSER_ORPHANS:
        return RepairActionExecuteResult(
            action_id=action_id,
            status="not_executable",
            changed=False,
            dry_run=request.dry_run,
            message="This repair action is advisory only and cannot be executed automatically.",
        )

    from myrm_agent_harness.toolkits.browser import (
        cleanup_orphan_processes,
        find_orphan_automation_processes,
    )

    orphans = await asyncio.to_thread(find_orphan_automation_processes)
    orphan_pids: list[int] = [int(orphan["pid"]) for orphan in orphans if "pid" in orphan]
    if not orphan_pids:
        return RepairActionExecuteResult(
            action_id=action_id,
            status="skipped",
            changed=False,
            dry_run=request.dry_run,
            message="No orphan browser automation processes were found.",
            details={"orphans": []},
        )

    if not request.dry_run and not request.confirm:
        return RepairActionExecuteResult(
            action_id=action_id,
            status="confirmation_required",
            changed=False,
            dry_run=False,
            message="State-changing cleanup requires confirm=true.",
            details={"orphan_pids": orphan_pids},
        )

    result = cleanup_orphan_processes(orphan_pids, force=not request.dry_run)
    killed = int(result.get("killed", 0))
    return RepairActionExecuteResult(
        action_id=action_id,
        status="dry_run" if request.dry_run else "completed",
        changed=not request.dry_run and killed > 0,
        dry_run=request.dry_run,
        message=str(result.get("message", f"Processed {len(orphan_pids)} orphan browser process(es).")),
        details={
            "orphan_pids": orphan_pids,
            "killed": killed,
            "failed": result.get("failed", []),
        },
    )
