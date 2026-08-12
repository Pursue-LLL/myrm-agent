"""Real end-to-end integration test: checkpoint API + real ShadowGit store.

Non-mocked: exercises the actual harness shadow-git store through the HTTP
checkpoint API — the exact path fixed by the data-source unification (the API
now reads create_file_snapshot_store() instead of the hardcoded local fallback,
so snapshots taken by SnapshotInterceptor are visible here).

Covers: create → list → diff → restore (with pre-rollback) → delete (newest
only, CAS) → cleanup (keep most recent).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


pytestmark = [
    pytest.mark.skipif(not _git_available(), reason="git not found"),
]


@pytest.fixture(autouse=True)
def _isolated_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point the harness factory at a temp store and reset all caches.

    Note: ``from app.api.checkpoint import router`` yields the exported APIRouter
    instance, not the router module — its ``_file_snapshot_store`` global lives in
    ``app.api.checkpoint.router``, so it must be reset via importlib.
    """
    import importlib

    import myrm_agent_harness.agent.file_snapshot.factory as factory_mod

    router_mod = importlib.import_module("app.api.checkpoint.router")

    monkeypatch.setenv("MYRM_DATA_DIR", str(tmp_path / "myrm-data"))
    factory_mod._cached_store = None
    router_mod._file_snapshot_store = None
    yield
    factory_mod._cached_store = None
    router_mod._file_snapshot_store = None


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "app.py").write_text("def main(): pass\n")
    (ws / "config.yaml").write_text("key: value\n")
    return ws


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    app = build_minimal_app("checkpoint")
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_snapshot(async_client: httpx.AsyncClient, working_dir: str, description: str) -> str:
    resp = await async_client.post(
        "/api/v1/checkpoint/file-snapshot/create",
        json={"working_dir": working_dir, "description": description},
    )
    assert resp.status_code == 200
    return resp.json()["snapshot_id"]


async def _list_snapshot_ids(async_client: httpx.AsyncClient, working_dir: str) -> list[str]:
    resp = await async_client.get(
        "/api/v1/checkpoint/file-snapshot/list",
        params={"working_dir": working_dir},
    )
    assert resp.status_code == 200
    return [s["snapshot_id"] for s in resp.json()["snapshots"]]


@pytest.mark.asyncio
async def test_http_full_lifecycle_with_real_git_store(
    async_client: httpx.AsyncClient, workspace: Path
) -> None:
    """create → diff → restore (pre-rollback) → delete newest-only semantics."""
    sid = await _create_snapshot(async_client, str(workspace), "baseline")

    # list shows the manual snapshot with its description
    resp = await async_client.get(
        "/api/v1/checkpoint/file-snapshot/list",
        params={"working_dir": str(workspace)},
    )
    assert resp.status_code == 200
    listed = resp.json()["snapshots"]
    assert any(s["snapshot_id"] == sid for s in listed)
    assert next(s for s in listed if s["snapshot_id"] == sid)["description"] == "baseline"

    # modify the workspace, then diff must report the change
    (workspace / "app.py").write_text("def main(): print('v2')\n")
    resp = await async_client.get(f"/api/v1/checkpoint/file-snapshot/{sid}/diff")
    assert resp.status_code == 200
    assert resp.json()["total_changes"] > 0
    assert any(c["path"] == "app.py" for c in resp.json()["changes"])

    # restore reverts the file and creates a PRE_ROLLBACK snapshot
    resp = await async_client.post(
        "/api/v1/checkpoint/file-snapshot/restore",
        json={"snapshot_id": sid},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["pre_rollback_snapshot_id"] is not None
    assert (workspace / "app.py").read_text() == "def main(): pass\n"

    pre_id = body["pre_rollback_snapshot_id"]
    ids = await _list_snapshot_ids(async_client, str(workspace))
    assert pre_id in ids

    # intermediate snapshots are not deletable (linear commit chain)
    resp = await async_client.request("DELETE", f"/api/v1/checkpoint/file-snapshot/{sid}")
    assert resp.status_code == 404

    # newest snapshot (pre-rollback) is deletable
    resp = await async_client.request("DELETE", f"/api/v1/checkpoint/file-snapshot/{pre_id}")
    assert resp.status_code == 200

    # after removing the newest, the former head (sid) becomes deletable
    resp = await async_client.request("DELETE", f"/api/v1/checkpoint/file-snapshot/{sid}")
    assert resp.status_code == 200
    assert await _list_snapshot_ids(async_client, str(workspace)) == []


@pytest.mark.asyncio
async def test_cleanup_keeps_most_recent_through_http(
    async_client: httpx.AsyncClient, workspace: Path
) -> None:
    """cleanup prunes oldest snapshots, keeping the newest max_snapshots."""
    for i in range(6):
        (workspace / "app.py").write_text(f"def main(): print('v{i}')\n")
        await _create_snapshot(async_client, str(workspace), f"iter-{i}")

    ids_before = await _list_snapshot_ids(async_client, str(workspace))
    assert len(ids_before) == 6

    resp = await async_client.post(
        "/api/v1/checkpoint/file-snapshot/cleanup",
        params={"working_dir": str(workspace), "max_snapshots": 3},
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 3

    ids_after = await _list_snapshot_ids(async_client, str(workspace))
    assert len(ids_after) == 3
    assert ids_after == ids_before[:3]  # newest kept


@pytest.mark.asyncio
async def test_interceptor_snapshots_visible_via_api(async_client: httpx.AsyncClient, workspace: Path) -> None:
    """Snapshots taken by SnapshotInterceptor (same factory store) appear in the API list.

    Uses _safe_snapshot_with_lock directly instead of before_destructive_action:
    the latter runs the snapshot in a background task under a 3s timeout, which is
    unreliable inside a short-lived pytest event loop (the loop closes before the
    background task lands). The 3s-timeout dispatch itself is covered by unit tests.
    """
    from app.services.checkpoint.snapshot_service import SnapshotInterceptor

    interceptor = SnapshotInterceptor()
    ws = str(workspace)
    with patch.object(
        SnapshotInterceptor, "_emit_snapshot_event", new_callable=AsyncMock
    ):
        await interceptor._safe_snapshot_with_lock(
            workspace_path=ws,
            action_type="bash",
            chat_id="real-session-1",
            agent_id="unknown_agent",
            turn_id="turn-1",
            cache_key=(ws, "turn-1"),
            metadata={"agent_id": "unknown_agent"},
        )

    # the API reads the same store (data-source unification), so the
    # interceptor snapshot is visible via HTTP list.
    ids = await _list_snapshot_ids(async_client, ws)
    assert len(ids) >= 1

    # the snapshot is an automatic bash snapshot; no internal ids leaked
    resp = await async_client.get(
        "/api/v1/checkpoint/file-snapshot/list",
        params={"working_dir": ws},
    )
    snap = next(s for s in resp.json()["snapshots"] if s["snapshot_id"] in ids)
    assert snap["trigger"] == "execute_terminal"
    assert snap["description"] == ""
    assert "chat" not in snap["description"]
