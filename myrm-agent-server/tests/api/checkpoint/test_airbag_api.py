"""Unit and integration tests for Task Safety Airbag API endpoints."""

from __future__ import annotations

import subprocess
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.services.checkpoint.task_airbag_service import get_task_airbag_service
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("checkpoint")


@pytest.fixture
def git_dir(tmp_path: Path) -> Path:
    """Create a temporary initialized Git repository with initial commit."""
    subprocess.run(["git", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "tester@myrm.ai"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=str(tmp_path),
        check=True,
        capture_output=True,
    )
    test_file = tmp_path / "index.js"
    test_file.write_text("console.log('init');\n", encoding="utf-8")
    subprocess.run(["git", "add", "index.js"], cwd=str(tmp_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path), check=True, capture_output=True)
    return tmp_path


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=30.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_arm_and_get_status_airbag_api(async_client: httpx.AsyncClient, git_dir: Path) -> None:
    task_id = "test-task-api-01"

    # 1. Arm airbag
    arm_resp = await async_client.post(
        "/api/v1/checkpoint/airbag/arm",
        json={"task_id": task_id, "workspace_path": str(git_dir)},
    )
    assert arm_resp.status_code == 200
    data = arm_resp.json()
    assert data["success"] is True
    assert data["task_id"] == task_id
    assert data["is_git_repo"] is True
    assert data["base_snapshot_id"] is not None

    # Mutate workspace
    (git_dir / "index.js").write_text("console.log('mutated');\n", encoding="utf-8")
    (git_dir / "draft.txt").write_text("new draft\n", encoding="utf-8")

    # Record external effect
    service = get_task_airbag_service()
    service.record_external_effect(task_id, "docker run -d postgres:latest")

    # 2. Query status
    status_resp = await async_client.get(
        f"/api/v1/checkpoint/airbag/{task_id}/status?workspace_path={git_dir}"
    )
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["task_id"] == task_id
    assert status_data["total_files_changed"] >= 1
    assert "docker run -d postgres:latest" in status_data["external_effects"]
    assert status_data["can_rollback"] is True

    # 3. Rollback
    rollback_resp = await async_client.post(
        "/api/v1/checkpoint/airbag/rollback",
        json={"task_id": task_id, "workspace_path": str(git_dir)},
    )
    assert rollback_resp.status_code == 200
    rb_data = rollback_resp.json()
    assert rb_data["status"] == "rolled_back"
    assert rb_data["rescue_snapshot_id"] is not None
    assert (git_dir / "index.js").read_text(encoding="utf-8") == "console.log('init');\n"

    # 4. Dismiss
    dismiss_resp = await async_client.post(
        "/api/v1/checkpoint/airbag/dismiss",
        json={"task_id": task_id, "workspace_path": str(git_dir)},
    )
    assert dismiss_resp.status_code == 200
    assert dismiss_resp.json()["status"] == "dismissed"


@pytest.mark.asyncio
async def test_airbag_not_found(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.get("/api/v1/checkpoint/airbag/non-existent-task/status")
    assert resp.status_code == 404
