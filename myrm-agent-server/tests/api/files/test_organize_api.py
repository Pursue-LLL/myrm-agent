"""Tests for workspace organize HITL API endpoints."""

from __future__ import annotations

import os

import pytest
from httpx import ASGITransport, AsyncClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="files")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def workspace_dir(tmp_path):
    scope = tmp_path / "inbox"
    scope.mkdir()
    (scope / "note.md").write_text("# Note", encoding="utf-8")
    return str(tmp_path)


def _plan_payload(workspace: str) -> dict[str, object]:
    return {
        "workspace": workspace,
        "plan": {
            "version": 1,
            "scope_root": "inbox",
            "preset": "project",
            "items": [
                {
                    "src": "inbox/note.md",
                    "dst": "inbox/docs/note.md",
                    "reason": "group markdown",
                },
            ],
        },
    }


@pytest.mark.anyio
async def test_organize_apply_dry_run(client: AsyncClient, workspace_dir: str):
    resp = await client.post(
        "/api/v1/files/organize/apply?dryRun=true",
        json=_plan_payload(workspace_dir),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["ok"] is True
    assert data["dryRun"] is True
    assert data["appliedCount"] == 1
    assert not os.path.exists(os.path.join(workspace_dir, "inbox", "docs", "note.md"))


@pytest.mark.anyio
async def test_organize_apply_and_rollback(client: AsyncClient, workspace_dir: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("MYRM_DATA_DIR", os.path.join(workspace_dir, "data"))
    apply_resp = await client.post(
        "/api/v1/files/organize/apply?dryRun=false",
        json=_plan_payload(workspace_dir),
    )
    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()["data"]
    assert apply_data["ok"] is True
    job_id = apply_data["jobId"]
    assert os.path.isfile(os.path.join(workspace_dir, "inbox", "docs", "note.md"))

    latest_resp = await client.get(
        "/api/v1/files/organize/latest-job",
        params={"workspace": workspace_dir},
    )
    assert latest_resp.status_code == 200
    assert latest_resp.json()["data"]["job"]["jobId"] == job_id

    rollback_resp = await client.post(f"/api/v1/files/organize/rollback/{job_id}")
    assert rollback_resp.status_code == 200
    rollback_data = rollback_resp.json()["data"]
    assert rollback_data["jobStatus"] == "rolled_back"
    assert os.path.isfile(os.path.join(workspace_dir, "inbox", "note.md"))
