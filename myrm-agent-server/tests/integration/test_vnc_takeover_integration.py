"""Integration test for VNC takeover lifecycle API.

Tests the full HTTP request cycle: takeover → resume, verifying
the TakeoverCoordinator state machine transitions correctly via API and
that the process-wide UserControl follows it (the Agent's browser/desktop
tools wait exactly while a person holds control).
Does NOT require actual VNC hardware — exercises the coordinator logic
through FastAPI endpoints.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.utils.runtime.user_control import get_user_control

from app.api.webui.vnc_routes import router


@pytest.fixture
def client() -> TestClient:
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/webui")
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_coordinator() -> Iterator[None]:
    """Reset the module-level coordinator and hand the process-wide control back after each test."""
    import app.api.webui.vnc_routes as mod

    def _reset() -> None:
        mod._takeover_coordinator = None
        mod._pre_takeover_snapshot = ""
        mod._pre_takeover_url = ""
        mod._takeover_start_time = 0.0
        get_user_control().release()

    _reset()
    yield
    _reset()


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


class TestTakeoverStateAndUserControl:
    def test_get_reports_who_holds_control(self, client: TestClient) -> None:
        idle = client.get("/webui/vnc/takeover").json()
        assert idle["state"] == "agent_active"
        assert idle["remaining_s"] is None

        client.post("/webui/vnc/takeover", json={"reason": "test"})
        held = client.get("/webui/vnc/takeover").json()
        assert held["state"] == "user_takeover"
        assert held["remaining_s"] is not None and held["remaining_s"] <= 300

    def test_takeover_fences_agent_tools_until_resume(self, client: TestClient) -> None:
        control = get_user_control()
        generation = control.generation
        assert control.held is False

        client.post("/webui/vnc/takeover", json={"reason": "captcha"})
        assert control.held is True
        assert control.generation == generation

        client.post("/webui/vnc/resume")
        assert control.held is False
        assert control.generation == generation + 1

    def test_repeated_takeover_renews_without_changing_hands(self, client: TestClient) -> None:
        control = get_user_control()
        client.post("/webui/vnc/takeover", json={"reason": "first"})
        started_at = client.get("/webui/vnc/takeover").json()["started_at"]

        renewed = client.post("/webui/vnc/takeover", json={"reason": "heartbeat"}).json()

        assert renewed["state"] == "user_takeover"
        assert renewed["started_at"] == started_at
        assert control.held is True

    def test_resume_without_takeover_keeps_generation(self, client: TestClient) -> None:
        control = get_user_control()
        generation = control.generation

        client.post("/webui/vnc/resume")

        assert control.held is False
        assert control.generation == generation
