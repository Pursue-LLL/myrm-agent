"""Integration test for POST /agents/clarify-response endpoint."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.agent.streaming import ClarificationWaiter, _clarification_waiters


@pytest.fixture(autouse=True)
def _cleanup_waiters():
    _clarification_waiters.clear()
    yield
    _clarification_waiters.clear()


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()

    async def mock_get_deploy_identity() -> str:
        return "test-user"

    pass

    from app.api.agents.general_agent import router

    app.include_router(router, prefix="/api/v1/agents")
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


class TestClarifyResponseEndpoint:
    def test_no_pending_waiter_returns_404(self, client: TestClient):
        resp = client.post(
            "/api/v1/agents/clarify-response",
            json={"messageId": "nonexistent", "answer": "hello"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("code") == 404 or "No pending" in str(body)

    def test_resolve_pending_waiter(self, client: TestClient):
        waiter = ClarificationWaiter.register("msg-test-1")
        assert not waiter.is_resolved

        resp = client.post(
            "/api/v1/agents/clarify-response",
            json={"messageId": "msg-test-1", "answer": "my answer"},
        )
        assert resp.status_code == 200
        assert waiter.is_resolved

    def test_resolve_with_empty_answer_for_skip(self, client: TestClient):
        waiter = ClarificationWaiter.register("msg-test-2")

        resp = client.post(
            "/api/v1/agents/clarify-response",
            json={"messageId": "msg-test-2", "answer": ""},
        )
        assert resp.status_code == 200
        assert waiter.is_resolved

    def test_resolve_with_structured_answer(self, client: TestClient):
        waiter = ClarificationWaiter.register("msg-test-3")

        resp = client.post(
            "/api/v1/agents/clarify-response",
            json={
                "messageId": "msg-test-3",
                "answer": {"question_1": "alpha", "question_2": ["beta", "gamma"]},
            },
        )
        assert resp.status_code == 200
        assert waiter.is_resolved

    def test_camel_case_field_mapping(self, client: TestClient):
        """Verify camelCase request body is correctly mapped via alias_generator."""
        waiter = ClarificationWaiter.register("msg-camel")
        resp = client.post(
            "/api/v1/agents/clarify-response",
            json={"messageId": "msg-camel", "answer": "test"},
        )
        assert resp.status_code == 200
        assert waiter.is_resolved
