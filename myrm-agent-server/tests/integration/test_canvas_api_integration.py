"""Integration tests for Canvas API endpoints.

Tests the full CRUD lifecycle + snapshot/selection via TestClient.
No mocks on key paths — real DB + real filesystem operations.
Auth is bypassed via resolve_identity monkeypatch.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(autouse=True)
def _isolate_canvas_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect canvas data to temp dir for test isolation."""
    monkeypatch.setattr("app.services.canvas._paths.CANVAS_DATA_DIR", tmp_path)


@pytest.fixture
def client():
    """Create a TestClient with noop lifespan and auth bypass."""
    from app.core.security.auth.identity import ResolvedIdentity

    @asynccontextmanager
    async def _noop_lifespan(_a):
        yield

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan

    import app.core.security.auth.identity as auth_mod
    import app.middleware.auth as mw_auth

    original_resolve = auth_mod.resolve_identity
    original_mw_resolve = mw_auth.resolve_identity

    def _always_local(**_kwargs):
        return ResolvedIdentity(
            user_id="local-user",
            auth_source="loopback",
            client_ip="127.0.0.1",
            loopback=True,
            private_net=True,
        )

    auth_mod.resolve_identity = _always_local
    mw_auth.resolve_identity = _always_local

    try:
        yield TestClient(app)
    finally:
        app.router.lifespan_context = original_lifespan
        auth_mod.resolve_identity = original_resolve
        mw_auth.resolve_identity = original_mw_resolve


def _ok(resp_json: dict[str, Any]) -> Any:
    """Extract data from success_response wrapper."""
    assert resp_json.get("success") is True, f"API failed: {resp_json}"
    return resp_json["data"]


class TestCanvasCRUD:
    def test_create_and_list(self, client: TestClient) -> None:
        resp = client.post("/api/v1/canvas", json={"name": "Test Canvas"})
        assert resp.status_code == 200, resp.text
        canvas = _ok(resp.json())
        assert canvas["name"] == "Test Canvas"
        canvas_id = canvas["id"]

        resp = client.get("/api/v1/canvas")
        assert resp.status_code == 200
        canvases = _ok(resp.json())
        assert any(c["id"] == canvas_id for c in canvases)

    def test_get_canvas(self, client: TestClient) -> None:
        resp = client.post("/api/v1/canvas", json={"name": "Get Test"})
        canvas_id = _ok(resp.json())["id"]

        resp = client.get(f"/api/v1/canvas/{canvas_id}")
        assert resp.status_code == 200
        assert _ok(resp.json())["id"] == canvas_id

    def test_rename_canvas(self, client: TestClient) -> None:
        resp = client.post("/api/v1/canvas", json={"name": "Old Name"})
        canvas_id = _ok(resp.json())["id"]

        resp = client.put(f"/api/v1/canvas/{canvas_id}", json={"name": "New Name"})
        assert resp.status_code == 200
        assert _ok(resp.json())["id"] == canvas_id

        resp = client.get(f"/api/v1/canvas/{canvas_id}")
        assert _ok(resp.json())["name"] == "New Name"

    def test_delete_canvas(self, client: TestClient) -> None:
        resp = client.post("/api/v1/canvas", json={"name": "To Delete"})
        canvas_id = _ok(resp.json())["id"]

        resp = client.delete(f"/api/v1/canvas/{canvas_id}")
        assert resp.status_code == 200

        resp = client.get(f"/api/v1/canvas/{canvas_id}")
        assert resp.status_code == 404


class TestCanvasSnapshot:
    def test_save_and_load_snapshot(self, client: TestClient) -> None:
        resp = client.post("/api/v1/canvas", json={"name": "Snap Test"})
        canvas_id = _ok(resp.json())["id"]

        resp = client.put(
            f"/api/v1/canvas/{canvas_id}/snapshot",
            json={"snapshot": {"store": {"shape:1": {"type": "text"}}}},
        )
        assert resp.status_code == 200

        resp = client.get(f"/api/v1/canvas/{canvas_id}/snapshot")
        assert resp.status_code == 200
        data = _ok(resp.json())
        snapshot = data.get("snapshot", data)
        assert "shape:1" in snapshot.get("store", {})


class TestCanvasSelection:
    def test_save_and_load_selection(self, client: TestClient) -> None:
        resp = client.post("/api/v1/canvas", json={"name": "Sel Test"})
        canvas_id = _ok(resp.json())["id"]

        resp = client.put(
            f"/api/v1/canvas/{canvas_id}/selection",
            json={"selected_shapes": [{"id": "shape:abc"}]},
        )
        assert resp.status_code == 200

        resp = client.get(f"/api/v1/canvas/{canvas_id}/selection")
        assert resp.status_code == 200
        data = _ok(resp.json())
        assert len(data.get("selectedShapes", [])) == 1
