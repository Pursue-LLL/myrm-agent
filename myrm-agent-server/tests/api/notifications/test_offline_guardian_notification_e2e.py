"""E2E tests for Offline Guardian notifications (Item 5).

Validates:
1. SystemNotificationService creates offline_guardian notifications with correct fields
2. Notification API returns offline_guardian notifications with meta_data
3. Error-type notifications have correct structure for frontend routing
"""

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="notifications")


@pytest.fixture(scope="module")
def test_client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_offline_guardian_success_notification_full_chain(test_client: TestClient) -> None:
    """Full chain: create success notification → list API returns it with correct fields."""
    from app.services.infra.system_notification import SystemNotificationService

    nid = await SystemNotificationService.create_notification(
        title="Task Completed",
        message="Your background task has successfully completed. You can view the results in the chat.",
        type="success",
        source="offline_guardian",
        meta_data={
            "chat_id": "e2e-chat-001",
            "message_id": "e2e-msg-001",
            "action_url": "/e2e-chat-001",
        },
    )
    assert nid

    resp = test_client.get("/api/v1/notifications")
    assert resp.status_code == 200
    data = resp.json()

    items = data["items"]
    matched = [n for n in items if n["id"] == nid]
    assert len(matched) == 1

    notif = matched[0]
    assert notif["title"] == "Task Completed"
    assert notif["type"] == "success"
    assert notif["source"] == "offline_guardian"
    assert notif["is_read"] is False
    assert notif["meta_data"]["action_url"] == "/e2e-chat-001"
    assert notif["meta_data"]["chat_id"] == "e2e-chat-001"
    assert notif["meta_data"]["message_id"] == "e2e-msg-001"


@pytest.mark.asyncio
async def test_offline_guardian_error_notification_full_chain(test_client: TestClient) -> None:
    """Full chain: create error notification → list API returns it with correct error fields."""
    from app.services.infra.system_notification import SystemNotificationService

    nid = await SystemNotificationService.create_notification(
        title="Task Failed",
        message="Your background task encountered an error and could not complete. Please check the chat for details.",
        type="error",
        source="offline_guardian",
        meta_data={
            "chat_id": "e2e-chat-fail",
            "message_id": "e2e-msg-fail",
            "action_url": "/e2e-chat-fail",
        },
    )
    assert nid

    resp = test_client.get("/api/v1/notifications")
    assert resp.status_code == 200
    data = resp.json()

    items = data["items"]
    matched = [n for n in items if n["id"] == nid]
    assert len(matched) == 1

    notif = matched[0]
    assert notif["title"] == "Task Failed"
    assert notif["type"] == "error"
    assert notif["source"] == "offline_guardian"
    assert "429" not in notif["message"]
    assert "rate_limit" not in notif["message"]
    assert notif["meta_data"]["action_url"] == "/e2e-chat-fail"


@pytest.mark.asyncio
async def test_offline_guardian_resume_failure_notification_full_chain(test_client: TestClient) -> None:
    """Full chain: durable resume failure notification → API returns correct fields."""
    from app.services.infra.system_notification import SystemNotificationService

    nid = await SystemNotificationService.create_notification(
        title="Task Resume Failed",
        message="A background task could not be resumed after a server restart. Please retry from the chat.",
        type="error",
        source="offline_guardian",
        meta_data={
            "chat_id": "e2e-chat-resume",
            "action_url": "/e2e-chat-resume",
        },
    )
    assert nid

    resp = test_client.get("/api/v1/notifications")
    assert resp.status_code == 200
    data = resp.json()

    items = data["items"]
    matched = [n for n in items if n["id"] == nid]
    assert len(matched) == 1

    notif = matched[0]
    assert notif["title"] == "Task Resume Failed"
    assert notif["type"] == "error"
    assert notif["source"] == "offline_guardian"
    assert notif["meta_data"]["action_url"] == "/e2e-chat-resume"


@pytest.mark.asyncio
async def test_notification_mark_read_works_for_offline_guardian(test_client: TestClient) -> None:
    """Offline guardian notifications can be marked as read via API."""
    from app.services.infra.system_notification import SystemNotificationService

    nid = await SystemNotificationService.create_notification(
        title="Task Completed",
        message="Done.",
        type="success",
        source="offline_guardian",
        meta_data={"chat_id": "e2e-read-test", "action_url": "/e2e-read-test"},
    )
    assert nid

    resp = test_client.post(f"/api/v1/notifications/{nid}/read")
    assert resp.status_code == 200

    resp = test_client.get("/api/v1/notifications")
    items = resp.json()["items"]
    matched = [n for n in items if n["id"] == nid]
    assert len(matched) == 1
    assert matched[0]["is_read"] is True
