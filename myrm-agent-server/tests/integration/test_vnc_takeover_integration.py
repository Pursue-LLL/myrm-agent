"""Integration test for VNC takeover lifecycle API.

Tests the full HTTP request cycle: takeover → resume, verifying
the TakeoverCoordinator state machine transitions correctly via API.
Does NOT require actual VNC hardware — exercises the coordinator logic
through FastAPI endpoints.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.webui.vnc_routes import router


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/webui")
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_coordinator() -> None:
    """Reset the module-level coordinator between tests."""
    import app.api.webui.vnc_routes as mod

    mod._takeover_coordinator = None
    mod._pre_takeover_snapshot = ""
    mod._pre_takeover_url = ""
    mod._takeover_start_time = 0.0


class TestVncTakeoverApiIntegration:
    def test_takeover_transitions_to_user_takeover(self, client: TestClient) -> None:
        resp = client.post("/webui/vnc/takeover", json={"reason": "user stuck on login"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "user_takeover"
        assert data["started_at"] is not None
        assert data["timeout_s"] == 300
        assert data["remaining_s"] is not None and data["remaining_s"] <= 300

    def test_resume_transitions_back_to_agent_active(self, client: TestClient) -> None:
        client.post("/webui/vnc/takeover", json={"reason": "test"})

        resp = client.post("/webui/vnc/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "agent_active"
        assert data["started_at"] is None
        assert data["remaining_s"] is None

    def test_takeover_is_idempotent(self, client: TestClient) -> None:
        resp1 = client.post("/webui/vnc/takeover", json={"reason": "first"})
        resp2 = client.post("/webui/vnc/takeover", json={"reason": "second"})
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["state"] == "user_takeover"
        assert resp2.json()["state"] == "user_takeover"

    def test_resume_without_takeover_is_noop(self, client: TestClient) -> None:
        resp = client.post("/webui/vnc/resume")
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "agent_active"
        assert data["learned"] is False

    def test_takeover_empty_body_accepted(self, client: TestClient) -> None:
        resp = client.post("/webui/vnc/takeover")
        assert resp.status_code == 200
        assert resp.json()["state"] == "user_takeover"

    def test_full_takeover_resume_cycle(self, client: TestClient) -> None:
        """Full cycle: takeover → verify state → resume → verify state."""
        take_resp = client.post("/webui/vnc/takeover", json={"reason": "demo"})
        assert take_resp.json()["state"] == "user_takeover"

        resume_resp = client.post("/webui/vnc/resume")
        data = resume_resp.json()
        assert data["state"] == "agent_active"
        assert data["learned"] is False

    def test_learned_flag_when_pre_snapshot_exists(self, client: TestClient) -> None:
        """When pre_snapshot is captured, resume should return learned=True."""
        import app.api.webui.vnc_routes as mod

        client.post("/webui/vnc/takeover", json={"reason": "test"})

        mod._pre_takeover_snapshot = "aria: heading 'Page'"

        resp = client.post("/webui/vnc/resume")
        data = resp.json()
        assert data["learned"] is True
