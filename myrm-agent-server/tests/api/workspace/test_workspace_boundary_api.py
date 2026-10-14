"""[INPUT]
FastAPI app, workspace_boundary_router, TestClient
[OUTPUT]
Integration tests for Workspace Execution Boundary and 3-Currents Handshake API.
[POS]
tests/api/workspace/test_workspace_boundary_api.py
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.workspace.workspace_boundary_router import router as boundary_router
from app.services.workspace.boundary.workspace_boundary_service import (
    WorkspaceBoundaryInspectorService,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    test_app = FastAPI(title="Workspace Boundary Test App")
    test_app.include_router(boundary_router, prefix="/api/v1/workspace")
    return TestClient(test_app, raise_server_exceptions=False)


def test_get_current_boundary(client: TestClient, tmp_path: Path) -> None:
    response = client.get(
        "/api/v1/workspace/boundary/current",
        params={
            "session_id": "test-sess-001",
            "project_id": "proj-agent-core",
            "project_name": "Agent Core Engine",
            "session_goal": "Implement Item 58 HUD",
            "cwd": str(tmp_path),
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "test-sess-001"
    assert data["project_id"] == "proj-agent-core"
    assert data["project_name"] == "Agent Core Engine"
    assert data["session_goal"] == "Implement Item 58 HUD"
    assert data["cwd"] == str(tmp_path)
    assert data["execution_host_type"] in ["local_host", "cloud_sandbox", "docker_container"]
    assert "inspected_at" in data
    assert "git_branch" in data


def test_handshake_target_path_exists(client: TestClient, tmp_path: Path) -> None:
    target_dir = tmp_path / "valid_workspace"
    target_dir.mkdir()

    payload = {
        "target_project_id": "target-proj-101",
        "target_path": str(target_dir),
        "current_session_id": "sess-prev",
    }

    response = client.post("/api/v1/workspace/boundary/handshake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["target_project_id"] == "target-proj-101"
    assert data["path_exists"] is True
    assert data["can_switch"] is True
    assert len(data["handshake_token"]) > 0
    # Directory is not a git repo initially
    assert data["risk_level"] in ["safe", "warning"]


def test_handshake_target_path_not_found(client: TestClient, tmp_path: Path) -> None:
    non_existent = tmp_path / "phantom_dir"

    payload = {
        "target_project_id": "target-proj-404",
        "target_path": str(non_existent),
    }

    response = client.post("/api/v1/workspace/boundary/handshake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["path_exists"] is False
    assert data["can_switch"] is False
    assert data["risk_level"] == "blocked"
    assert any("does not exist" in w for w in data["warnings"])
    assert data["handshake_token"] == ""


def test_handshake_target_is_file_blocked(client: TestClient, tmp_path: Path) -> None:
    file_path = tmp_path / "not_a_dir.txt"
    file_path.write_text("dummy", encoding="utf-8")

    payload = {
        "target_project_id": "target-proj-file",
        "target_path": str(file_path),
    }

    response = client.post("/api/v1/workspace/boundary/handshake", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["path_exists"] is True
    assert data["can_switch"] is False
    assert data["risk_level"] == "blocked"
    assert any("not a directory" in w for w in data["warnings"])


def test_list_worktrees(client: TestClient, tmp_path: Path) -> None:
    response = client.get(
        "/api/v1/workspace/boundary/worktrees",
        params={"cwd": str(tmp_path)},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_cloud_sandbox_host_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANDBOX_ID", "sbx-alpha-99")
    service = WorkspaceBoundaryInspectorService()
    host_type, label, host_id = service.detect_host_execution_topology()
    assert host_type == "cloud_sandbox"
    assert "sbx-alpha-99" in label
    assert host_id == "sbx-alpha-99"
