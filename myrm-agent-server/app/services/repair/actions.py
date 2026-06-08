"""White-listed runtime repair actions.

[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: framework health report)
- myrm_agent_harness.toolkits.browser::* (POS: browser orphan process maintenance)

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

from enum import StrEnum
from typing import TYPE_CHECKING

from myrm_agent_harness.observability.diagnostics.protocols import HealthReport
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager


class RepairActionId(StrEnum):
    """Known repair actions exposed to GUI clients."""

    CLEANUP_BROWSER_ORPHANS = "cleanup_browser_orphans"
    REVIEW_CHANNEL_DLQ = "review_channel_dlq"
    REVIEW_WORKSPACE_STORAGE = "review_workspace_storage"
    REVIEW_RUNTIME_DEPENDENCY = "review_runtime_dependency"
    SQLITE_BACKUP_NOW = "sqlite_backup_now"
    SQLITE_RESTORE_LATEST = "sqlite_restore_latest"


class RepairRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RepairScope(StrEnum):
    CURRENT_RUNTIME = "current_runtime"
    CURRENT_WORKSPACE = "current_workspace"
    INTEGRATION = "integration"
    PLATFORM_SANDBOX = "platform_sandbox"


class RepairAction(BaseModel):
    """A GUI-safe, auditable repair recommendation."""

    action_id: RepairActionId
    title: str
    description: str
    component: str
    layer: str
    scope: RepairScope
    risk_level: RepairRiskLevel
    requires_approval: bool = True
    dry_run_supported: bool = True
    executable: bool
    method: str | None = None
    endpoint: str | None = None
    confirm_required: bool = True
    reason: str
    expected_effect: str
    does_not_do: list[str] = Field(default_factory=list)


class RepairActionExecuteRequest(BaseModel):
    """Execution request for a white-listed repair action."""

    dry_run: bool = Field(default=True, description="Preview the action without changing runtime state.")
    confirm: bool = Field(default=False, description="Required for state-changing execution.")


class RepairActionExecuteResult(BaseModel):
    """Execution result for a white-listed repair action."""

    action_id: RepairActionId
    status: str
    changed: bool
    dry_run: bool
    message: str
    details: dict[str, object] = Field(default_factory=dict)


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
            does_not_do=["Does not modify database files.", "Does not delete workspace content."],
        )

    if report.component_name in {"Network", "VectorDB", "SystemResources", "AgentEngine"}:
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
            does_not_do=["Does not run shell commands.", "Does not change configuration automatically."],
        )

    return None


async def _browser_orphan_action() -> RepairAction | None:
    try:
        from myrm_agent_harness.toolkits.browser import find_orphan_chromium_processes
    except ImportError:
        return None

    orphans = find_orphan_chromium_processes()
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
        does_not_do=["Does not close normal user browser windows.", "Does not delete browser profiles or workspace files."],
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

    browser_action = await _browser_orphan_action()
    if browser_action is not None:
        actions.append(browser_action)

    sqlite_action = _sqlite_backup_action()
    if sqlite_action is not None:
        actions.append(sqlite_action)

    return _dedupe(actions)


def _sqlite_backup_action() -> RepairAction | None:
    from pathlib import Path

    try:
        from app.config.settings import settings

        db_path = Path(settings.database.sqlite_path)
        if not db_path.exists():
            return None
    except Exception:
        return None

    return RepairAction(
        action_id=RepairActionId.SQLITE_BACKUP_NOW,
        title="Create SQLite backup",
        description="Create a hot-backup of the SQLite database for disaster recovery.",
        component="Database",
        layer="server",
        scope=RepairScope.CURRENT_WORKSPACE,
        risk_level=RepairRiskLevel.LOW,
        requires_approval=False,
        executable=True,
        method="POST",
        endpoint=f"/health/repair-actions/{RepairActionId.SQLITE_BACKUP_NOW.value}/execute",
        reason="Periodic backup ensures data can be recovered after corruption.",
        expected_effect="Creates a verified backup snapshot with SHA-256 checksum.",
        does_not_do=["Does not modify the live database.", "Does not block agent execution."],
    )


async def execute_repair_action(action_id: RepairActionId, request: RepairActionExecuteRequest) -> RepairActionExecuteResult:
    """Execute a white-listed repair action."""

    if action_id == RepairActionId.SQLITE_BACKUP_NOW:
        return _execute_sqlite_backup(request)

    if action_id == RepairActionId.SQLITE_RESTORE_LATEST:
        return _execute_sqlite_restore(request)

    if action_id != RepairActionId.CLEANUP_BROWSER_ORPHANS:
        return RepairActionExecuteResult(
            action_id=action_id,
            status="not_executable",
            changed=False,
            dry_run=request.dry_run,
            message="This repair action is advisory only and cannot be executed automatically.",
        )

    from myrm_agent_harness.toolkits.browser import cleanup_orphan_processes, find_orphan_chromium_processes

    orphans = find_orphan_chromium_processes()
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


def _get_sqlite_backup_manager() -> "SQLiteBackupManager | None":
    from app.database.backup import get_sqlite_backup_manager

    return get_sqlite_backup_manager()


def _execute_sqlite_backup(request: RepairActionExecuteRequest) -> RepairActionExecuteResult:
    if request.dry_run:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_BACKUP_NOW,
            status="dry_run",
            changed=False,
            dry_run=True,
            message="Would create a hot-backup of the SQLite database.",
        )

    try:
        manager = _get_sqlite_backup_manager()
        if manager is None:
            return RepairActionExecuteResult(
                action_id=RepairActionId.SQLITE_BACKUP_NOW,
                status="failed",
                changed=False,
                dry_run=False,
                message="Cannot backup: database is in-memory or file not found",
            )
        record = manager.create_backup()
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_BACKUP_NOW,
            status="completed",
            changed=True,
            dry_run=False,
            message=f"Backup created: {record.file_name} ({record.size_bytes} bytes)",
            details={
                "backup_id": record.backup_id,
                "file_name": record.file_name,
                "size_bytes": record.size_bytes,
                "checksum": record.checksum_sha256[:16] + "…",
            },
        )
    except Exception as exc:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_BACKUP_NOW,
            status="failed",
            changed=False,
            dry_run=False,
            message=f"Backup failed: {exc}",
        )


def _execute_sqlite_restore(request: RepairActionExecuteRequest) -> RepairActionExecuteResult:
    if request.dry_run:
        manager = _get_sqlite_backup_manager()
        backups = manager.list_backups() if manager else []
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="dry_run",
            changed=False,
            dry_run=True,
            message=f"Would restore from latest backup ({len(backups)} available).",
            details={"available_backups": len(backups)},
        )

    if not request.confirm:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="confirmation_required",
            changed=False,
            dry_run=False,
            message="Database restore requires confirm=true. This will replace the current database.",
        )

    try:
        manager = _get_sqlite_backup_manager()
        if manager is None:
            return RepairActionExecuteResult(
                action_id=RepairActionId.SQLITE_RESTORE_LATEST,
                status="failed",
                changed=False,
                dry_run=False,
                message="Cannot restore: database is in-memory or file not found",
            )
        result = manager.restore_latest()
        if result.restored:
            return RepairActionExecuteResult(
                action_id=RepairActionId.SQLITE_RESTORE_LATEST,
                status="completed",
                changed=True,
                dry_run=False,
                message=f"Database restored from {result.snapshot_file}",
                details={
                    "snapshot": result.snapshot_file,
                    "quarantine": result.quarantine_dir,
                },
            )
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="failed",
            changed=False,
            dry_run=False,
            message=f"Restore failed: {result.error}",
        )
    except Exception as exc:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="failed",
            changed=False,
            dry_run=False,
            message=f"Restore failed: {exc}",
        )
