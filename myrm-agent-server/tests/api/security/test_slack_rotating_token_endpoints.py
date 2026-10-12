"""API endpoint tests for Slack Rotating Token Classification and Scope Inspection."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.slack_rotating_token_router import (
    router as slack_rotating_token_router,
)


@pytest.fixture
def test_client() -> TestClient:
    """Fixture providing test client mounting slack_rotating_token_router."""
    app = FastAPI()
    app.include_router(slack_rotating_token_router, prefix="/api/v1/security")
    return TestClient(app)


def test_classify_endpoint_success(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/slack-rotating-token/classify",
        json={
            "token_or_auth_header": "Bearer xoxe.xoxb-test-rot-token",
            "raw_token_type_hint": None,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bot"
    assert data["category"] == "rotating"
    assert data["is_rotating"] is True
    assert data["prefix_matched"] == "xoxe.xoxb-"
    assert data["normalized_token"] == "xoxe.xoxb-test-rot-token"
    assert data["is_bearer_wrapped"] is True


def test_classify_endpoint_static_user(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/slack-rotating-token/classify",
        json={
            "token_or_auth_header": "xoxp-static-user-999",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "user"
    assert data["category"] == "static"
    assert data["is_rotating"] is False
    assert data["prefix_matched"] == "xoxp-"
    assert data["is_bearer_wrapped"] is False


def test_inspect_scopes_endpoint_bot(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/slack-rotating-token/inspect-scopes",
        json={
            "token_type": "bot",
            "metadata": {"scope": "app_mentions:read chat:write files:write"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "bot"
    assert data["resolved_scopes"] == [
        "app_mentions:read",
        "chat:write",
        "files:write",
    ]
    assert data["source_field"] == "scope"


def test_inspect_scopes_endpoint_user(test_client: TestClient) -> None:
    resp = test_client.post(
        "/api/v1/security/slack-rotating-token/inspect-scopes",
        json={
            "token_type": "user",
            "metadata": {"authed_user": {"scope": "users:read,channels:history"}},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["token_type"] == "user"
    assert data["resolved_scopes"] == [
        "channels:history",
        "users:read",
    ]
    assert data["source_field"] == "authed_user.scope"
