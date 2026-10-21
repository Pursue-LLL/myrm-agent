"""[INPUT]
- TestClient from starlette/fastapi test suite
- Workbench API routes under /api/v1/workbench

[OUTPUT]
- Unit tests verifying workspace file tree, file content, unified diff, terminal exec & plugin probe

[POS]
Unit tests for Independent Multi-Tab Auxiliary Workbench backend (Item 25).
Strict typing: Zero Any. File length < 180 lines.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.workbench.routes import workbench_router


@pytest.fixture
def workbench_client() -> TestClient:
    app = FastAPI()
    app.include_router(workbench_router, prefix="/api/v1/workbench")
    return TestClient(app)


def test_list_workspace_files(workbench_client: TestClient) -> None:
    """Test retrieving workspace file tree."""
    response = workbench_client.get("/api/v1/workbench/files?max_depth=2")
    assert response.status_code == 200
    data = response.json()

    assert "root_path" in data
    assert "nodes" in data
    assert isinstance(data["nodes"], list)
    assert "total_files" in data
    assert "total_dirs" in data


def test_list_workspace_files_path_traversal_blocked(workbench_client: TestClient) -> None:
    """Test path traversal attack is rejected with 403."""
    response = workbench_client.get("/api/v1/workbench/files?root_dir=../../../../etc")
    assert response.status_code == 403
    assert "traversal forbidden" in response.json()["detail"].lower()


def test_get_file_content_success_and_not_found(workbench_client: TestClient, tmp_path: Path) -> None:
    """Test reading file content and 404 on missing file."""
    # Test 404 missing
    missing_resp = workbench_client.get("/api/v1/workbench/file/content?path=non_existent_file_xyz.py")
    assert missing_resp.status_code == 404

    # Test reading existing pyproject.toml
    resp = workbench_client.get("/api/v1/workbench/file/content?path=pyproject.toml")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path"] == "pyproject.toml"
    assert data["language"] == "toml"
    assert "content" in data
    assert len(data["content"]) > 0


def test_compute_file_diff(workbench_client: TestClient) -> None:
    """Test generating structured unified diff and hunk statistics."""
    payload = {
        "file_path": "src/demo.py",
        "original_content": "def hello():\n    print('old')\n",
        "modified_content": "def hello():\n    print('new')\n    return True\n",
    }
    response = workbench_client.post("/api/v1/workbench/diff", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["file_path"] == "src/demo.py"
    assert data["additions"] == 2
    assert data["deletions"] == 1
    assert "hunks" in data
    assert len(data["hunks"]) >= 1
    assert "-    print('old')" in data["unified_diff"]
    assert "+    print('new')" in data["unified_diff"]


def test_execute_terminal_command(workbench_client: TestClient) -> None:
    """Test executing controlled shell command and safety interception."""
    # Safe command execution
    payload = {"command": "echo 'myrm workbench ok'", "timeout_seconds": 10}
    response = workbench_client.post("/api/v1/workbench/terminal/exec", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["exit_code"] == 0
    assert "myrm workbench ok" in data["stdout"]
    assert data["duration_ms"] >= 0

    # High-risk command interception
    danger_payload = {"command": "rm -rf /", "timeout_seconds": 5}
    danger_resp = workbench_client.post("/api/v1/workbench/terminal/exec", json=danger_payload)
    assert danger_resp.status_code == 400
    assert "sandbox guard" in danger_resp.json()["detail"].lower()


def test_list_and_probe_plugins(workbench_client: TestClient) -> None:
    """Test listing plugins and executing probe check."""
    # List plugins
    list_resp = workbench_client.get("/api/v1/workbench/plugins")
    assert list_resp.status_code == 200
    plugins = list_resp.json()
    assert isinstance(plugins, list)
    assert len(plugins) >= 1

    target_id = plugins[0]["plugin_id"]

    # Probe plugin
    probe_resp = workbench_client.post(f"/api/v1/workbench/plugins/{target_id}/probe")
    assert probe_resp.status_code == 200
    probe_data = probe_resp.json()
    assert probe_data["plugin_id"] == target_id
    assert probe_data["status"] == "healthy"
    assert probe_data["latency_ms"] >= 0

    # Probe non-existent plugin
    not_found_resp = workbench_client.post("/api/v1/workbench/plugins/unknown-plugin-999/probe")
    assert not_found_resp.status_code == 404
