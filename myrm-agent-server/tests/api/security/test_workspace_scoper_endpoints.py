"""Integration tests for Per-Task Workspace Scoping API endpoints."""

from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.workspace_scoper_router import router as workspace_scoper_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting workspace_scoper_router."""
    test_app = FastAPI(title="Workspace Scoper Test App")
    test_app.include_router(workspace_scoper_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_workspace_scoper_endpoints_lifecycle(client: TestClient) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace_dir = os.path.join(tmpdir, "task_project")
        other_dir = os.path.join(tmpdir, "other_project")
        os.makedirs(workspace_dir, exist_ok=True)
        os.makedirs(other_dir, exist_ok=True)

        task_id = "task_test_lifecycle_99"

        # 1. Bind workspace
        bind_resp = client.post(
            "/api/v1/security/workspace/bind",
            json={
                "task_id": task_id,
                "workspace_root": workspace_dir,
                "access_mode": "scoped_strict",
            },
        )
        assert bind_resp.status_code == 201
        bind_data = bind_resp.json()
        assert bind_data["task_id"] == task_id
        assert bind_data["access_mode"] == "scoped_strict"

        # 2. Get binding
        get_resp = client.get(f"/api/v1/security/workspace/{task_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["workspace_root"] == os.path.abspath(workspace_dir)

        # 3. Verify internal file access (allowed)
        internal_file = os.path.join(workspace_dir, "report.md")
        verify_resp_1 = client.post(
            f"/api/v1/security/workspace/{task_id}/verify-access",
            json={"target_path": internal_file, "action": "read"},
        )
        assert verify_resp_1.status_code == 200
        assert verify_resp_1.json()["allowed"] is True

        # 4. Verify external file access (blocked in scoped_strict)
        external_file = os.path.join(other_dir, "database.db")
        verify_resp_2 = client.post(
            f"/api/v1/security/workspace/{task_id}/verify-access",
            json={"target_path": external_file, "action": "read"},
        )
        assert verify_resp_2.status_code == 200
        assert verify_resp_2.json()["allowed"] is False

        # 5. Switch mode to full_system_access
        mode_resp = client.post(
            f"/api/v1/security/workspace/{task_id}/mode",
            json={"access_mode": "full_system_access"},
        )
        assert mode_resp.status_code == 200
        assert mode_resp.json()["access_mode"] == "full_system_access"

        # 6. Verify external access again (allowed now)
        verify_resp_3 = client.post(
            f"/api/v1/security/workspace/{task_id}/verify-access",
            json={"target_path": external_file, "action": "read"},
        )
        assert verify_resp_3.status_code == 200
        assert verify_resp_3.json()["allowed"] is True

        # 7. Retrieve audit report
        audit_resp = client.get(f"/api/v1/security/workspace/{task_id}/audit-report")
        assert audit_resp.status_code == 200
        report = audit_resp.json()
        assert report["total_accesses"] == 3
        assert report["violations_count"] == 1
        assert len(report["audit_entries"]) == 3
