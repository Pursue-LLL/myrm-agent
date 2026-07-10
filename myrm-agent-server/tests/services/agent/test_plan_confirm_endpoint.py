"""Integration test for POST /agents/plan-confirm-response endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.agent.streaming import PhaseWaiter, _phase_waiters


@pytest.fixture(autouse=True)
def _cleanup_waiters():
    _phase_waiters.clear()
    yield
    _phase_waiters.clear()


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    from app.api.agents.general_agent import router

    app.include_router(router, prefix="/api/v1/agents")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestPlanConfirmEndpoint:
    def test_no_pending_waiter_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/plan-confirm-response",
            json={"messageId": "nonexistent", "action": "confirm"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("code") == 404 or "No pending" in str(body)

    def test_confirm_action_resolves_with_none(self, client: TestClient):
        waiter = PhaseWaiter.register("plan:msg-plan-1")
        assert not waiter.is_resolved

        resp = client.post(
            "/api/v1/agents/plan-confirm-response",
            json={"messageId": "msg-plan-1", "action": "confirm"},
        )
        assert resp.status_code == 200
        assert waiter.is_resolved
        assert waiter._answer is None

    def test_edit_action_resolves_with_modified_plan(self, client: TestClient):
        waiter = PhaseWaiter.register("plan:msg-plan-2")

        resp = client.post(
            "/api/v1/agents/plan-confirm-response",
            json={
                "messageId": "msg-plan-2",
                "action": "edit",
                "modifiedPlan": "New plan step 1\nNew plan step 2",
            },
        )
        assert resp.status_code == 200
        assert waiter.is_resolved
        assert waiter._answer == "New plan step 1\nNew plan step 2"

    def test_skip_action_resolves_with_none(self, client: TestClient):
        waiter = PhaseWaiter.register("plan:msg-plan-3")

        resp = client.post(
            "/api/v1/agents/plan-confirm-response",
            json={"messageId": "msg-plan-3", "action": "skip"},
        )
        assert resp.status_code == 200
        assert waiter.is_resolved
        assert waiter._answer is None

    def test_edit_without_modified_plan_resolves_with_none(self, client: TestClient):
        waiter = PhaseWaiter.register("plan:msg-plan-4")

        resp = client.post(
            "/api/v1/agents/plan-confirm-response",
            json={"messageId": "msg-plan-4", "action": "edit"},
        )
        assert resp.status_code == 200
        assert waiter.is_resolved
        assert waiter._answer is None

    def test_response_includes_action(self, client: TestClient):
        PhaseWaiter.register("plan:msg-plan-5")

        resp = client.post(
            "/api/v1/agents/plan-confirm-response",
            json={"messageId": "msg-plan-5", "action": "edit", "modifiedPlan": "updated"},
        )
        body = resp.json()
        assert body.get("data", {}).get("action") == "edit"
