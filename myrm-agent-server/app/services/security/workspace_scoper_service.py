"""Service for Per-Task Workspace Scoping and Cross-Contamination Guard.

[INPUT]
- BindWorkspaceRequest, UpdateAccessModeRequest, VerifyAccessRequest, task_id

[OUTPUT]
- WorkspaceBindingDto, VerifyAccessResponse, WorkspaceAuditReportDto

[POS]
- Server security service. Wraps harness workspace_scoper subsystem for REST API endpoints.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.core.security.workspace_scoper import (
    CrossWorkspaceContaminationError,
    FileAccessAction,
    WorkspaceAccessMode,
    WorkspaceBinding,
    WorkspaceContaminationGuard,
)

from app.schemas.workspace_scoper import (
    BindWorkspaceRequest,
    FileAccessAuditEntryDto,
    VerifyAccessResponse,
    WorkspaceAuditReportDto,
    WorkspaceBindingDto,
)


class WorkspaceScoperService:
    """Singleton service managing task workspace confinement and cross-task contamination prevention."""

    def __init__(self) -> None:
        self._guard = WorkspaceContaminationGuard()

    def bind_workspace(self, request: BindWorkspaceRequest) -> WorkspaceBindingDto:
        """Bind a task to an isolated directory root."""
        mode = WorkspaceAccessMode(request.access_mode)
        binding: WorkspaceBinding = self._guard.bind_task_workspace(
            task_id=request.task_id,
            workspace_root=request.workspace_root,
            access_mode=mode,
        )
        return WorkspaceBindingDto(
            task_id=binding.task_id,
            workspace_root=binding.workspace_root,
            access_mode=binding.access_mode.value,
            created_at=binding.created_at,
        )

    def get_binding(self, task_id: str) -> WorkspaceBindingDto | None:
        """Retrieve active workspace binding for a task."""
        binding = self._guard.get_binding(task_id)
        if not binding:
            return None
        return WorkspaceBindingDto(
            task_id=binding.task_id,
            workspace_root=binding.workspace_root,
            access_mode=binding.access_mode.value,
            created_at=binding.created_at,
        )

    def update_access_mode(self, task_id: str, access_mode: str) -> WorkspaceBindingDto:
        """Switch access mode between strict scoping and full system access."""
        mode = WorkspaceAccessMode(access_mode)
        binding = self._guard.update_access_mode(task_id, mode)
        return WorkspaceBindingDto(
            task_id=binding.task_id,
            workspace_root=binding.workspace_root,
            access_mode=binding.access_mode.value,
            created_at=binding.created_at,
        )

    def verify_access(
        self,
        task_id: str,
        target_path: str,
        action: str = "read",
    ) -> VerifyAccessResponse:
        """Verify whether task file access is contained inside its authorized workspace."""
        file_action = FileAccessAction(action)
        binding = self._guard.get_binding(task_id)
        if not binding:
            raise KeyError(f"No workspace binding found for task '{task_id}'")

        try:
            allowed = self._guard.verify_path_access(task_id, target_path, file_action)
            return VerifyAccessResponse(
                task_id=task_id,
                target_path=target_path,
                action=action,
                allowed=allowed,
                access_mode=binding.access_mode.value,
            )
        except CrossWorkspaceContaminationError:
            return VerifyAccessResponse(
                task_id=task_id,
                target_path=target_path,
                action=action,
                allowed=False,
                access_mode=binding.access_mode.value,
            )

    def get_audit_report(self, task_id: str) -> WorkspaceAuditReportDto:
        """Generate a complete audit summary of task file operations and containment integrity."""
        report = self._guard.generate_audit_report(task_id)
        entries_dto = [
            FileAccessAuditEntryDto(
                entry_id=e.entry_id,
                task_id=e.task_id,
                target_path=e.target_path,
                action=e.action.value,
                allowed=e.allowed,
                violation_reason=e.violation_reason,
                timestamp=e.timestamp,
            )
            for e in report.audit_entries
        ]
        return WorkspaceAuditReportDto(
            task_id=report.task_id,
            workspace_root=report.workspace_root,
            access_mode=report.access_mode.value,
            total_accesses=report.total_accesses,
            violations_count=report.violations_count,
            modified_files=list(report.modified_files),
            audit_entries=entries_dto,
            generated_at=report.generated_at,
        )

    def clear_task(self, task_id: str) -> None:
        """Clean up state for an archived task."""
        self._guard.clear_task(task_id)


_service_lock = threading.Lock()
_global_workspace_scoper_service: WorkspaceScoperService | None = None


def get_workspace_scoper_service() -> WorkspaceScoperService:
    """Retrieve or initialize the global WorkspaceScoperService singleton."""
    global _global_workspace_scoper_service
    if _global_workspace_scoper_service is None:
        with _service_lock:
            if _global_workspace_scoper_service is None:
                _global_workspace_scoper_service = WorkspaceScoperService()
    return _global_workspace_scoper_service
