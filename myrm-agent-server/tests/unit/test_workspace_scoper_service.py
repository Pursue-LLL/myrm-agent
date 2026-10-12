"""Unit tests for WorkspaceScoperService in server layer.

[POS]
Server unit tests verifying per-task workspace directory binding,
path containment checks, access mode switching, and audit dossier generation.
"""

from __future__ import annotations

import os
import tempfile

from app.schemas.workspace_scoper import BindWorkspaceRequest
from app.services.security.workspace_scoper_service import WorkspaceScoperService


def test_workspace_scoper_service_binding_and_access() -> None:
    service = WorkspaceScoperService()

    with tempfile.TemporaryDirectory() as tmpdir:
        task_root = os.path.join(tmpdir, "tax_filing_2026")
        other_root = os.path.join(tmpdir, "confidential_hr")
        os.makedirs(task_root, exist_ok=True)
        os.makedirs(other_root, exist_ok=True)

        # 1. Bind workspace
        bind_req = BindWorkspaceRequest(
            task_id="task_tax_01",
            workspace_root=task_root,
            access_mode="scoped_strict",
        )
        binding = service.bind_workspace(bind_req)
        assert binding.task_id == "task_tax_01"
        assert binding.access_mode == "scoped_strict"

        # 2. Permitted internal access
        internal_file = os.path.join(task_root, "form_w2.pdf")
        res_internal = service.verify_access(
            task_id="task_tax_01",
            target_path=internal_file,
            action="read",
        )
        assert res_internal.allowed is True
        assert res_internal.task_id == "task_tax_01"

        # 3. Blocked external access
        external_file = os.path.join(other_root, "salary_matrix.xlsx")
        res_external = service.verify_access(
            task_id="task_tax_01",
            target_path=external_file,
            action="read",
        )
        assert res_external.allowed is False


def test_workspace_scoper_service_mode_switch_and_audit() -> None:
    service = WorkspaceScoperService()

    with tempfile.TemporaryDirectory() as tmpdir:
        task_root = os.path.join(tmpdir, "audit_task")
        sys_root = os.path.join(tmpdir, "system_etc")
        os.makedirs(task_root, exist_ok=True)
        os.makedirs(sys_root, exist_ok=True)

        service.bind_workspace(
            BindWorkspaceRequest(task_id="task_audit_02", workspace_root=task_root)
        )

        sys_file = os.path.join(sys_root, "hosts.cfg")

        # In strict mode: blocked
        res_blocked = service.verify_access("task_audit_02", sys_file, "read")
        assert res_blocked.allowed is False

        # Switch to full system access
        updated = service.update_access_mode("task_audit_02", "full_system_access")
        assert updated.access_mode == "full_system_access"

        # In full access: allowed
        res_allowed = service.verify_access("task_audit_02", sys_file, "read")
        assert res_allowed.allowed is True

        # Check audit report
        report = service.get_audit_report("task_audit_02")
        assert report.total_accesses == 2
        assert report.violations_count == 1
        assert len(report.audit_entries) == 2
