from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def test_client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


async def _create_notification(
    title: str = "Test",
    message: str = "Test message",
    type_: str = "info",
    source: str = "test",
    meta_data: dict[str, object] | None = None,
) -> str:
    from app.services.infra.system_notification import SystemNotificationService

    return await SystemNotificationService.create_notification(
        title=title, message=message, type=type_, source=source, meta_data=meta_data
    )


@pytest.mark.asyncio
async def test_list_notifications(test_client: TestClient) -> None:
    nid = await _create_notification(title="List Test", meta_data={"action_url": "/chat/123"})
    assert nid

    resp = test_client.get("/api/v1/notifications")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert "unread_count" in data

    found = next((n for n in data["items"] if n["id"] == nid), None)
    assert found is not None
    assert found["title"] == "List Test"
    assert found["is_read"] is False
    assert found["meta_data"]["action_url"] == "/chat/123"


@pytest.mark.asyncio
async def test_list_notifications_pagination(test_client: TestClient) -> None:
    for i in range(3):
        await _create_notification(title=f"Page Test {i}")

    resp = test_client.get("/api/v1/notifications?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 2
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_mark_single_as_read(test_client: TestClient) -> None:
    nid = await _create_notification(title="Single Read")

    resp = test_client.post(f"/api/v1/notifications/{nid}/read")
    assert resp.status_code == 200

    resp = test_client.get("/api/v1/notifications")
    found = next((n for n in resp.json()["items"] if n["id"] == nid), None)
    assert found["is_read"] is True


@pytest.mark.asyncio
async def test_mark_already_read_returns_404(test_client: TestClient) -> None:
    nid = await _create_notification(title="Already Read")

    test_client.post(f"/api/v1/notifications/{nid}/read")

    resp = test_client.post(f"/api/v1/notifications/{nid}/read")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_nonexistent_returns_404(test_client: TestClient) -> None:
    resp = test_client.post("/api/v1/notifications/nonexistent_id_000/read")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_mark_all_as_read(test_client: TestClient) -> None:
    await _create_notification(title="MarkAll 1")
    await _create_notification(title="MarkAll 2")

    resp = test_client.post("/api/v1/notifications/read-all")
    assert resp.status_code == 200

    resp = test_client.get("/api/v1/notifications")
    assert resp.json()["unread_count"] == 0


@pytest.mark.asyncio
async def test_retry_no_delivery_id(test_client: TestClient) -> None:
    nid = await _create_notification(title="No DLQ", type_="error", meta_data={"foo": "bar"})

    resp = test_client.post(f"/api/v1/notifications/{nid}/retry")
    assert resp.status_code == 400
    assert "delivery_id" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_retry_nonexistent_notification(test_client: TestClient) -> None:
    resp = test_client.post("/api/v1/notifications/nonexistent_999/retry")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_dlq_notification(test_client: TestClient) -> None:
    nid = await _create_notification(
        title="DLQ Fail", type_="error", source="channel_gateway", meta_data={"delivery_id": "fake_dlq_123"}
    )

    resp = test_client.post(f"/api/v1/notifications/{nid}/retry")
    assert resp.status_code == 500
    assert "Failed to retry message" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_cleanup_old_notifications() -> None:
    from app.api.notifications.router import cleanup_old_notifications
    from app.database.connection import get_session
    from app.database.models import SystemNotification

    nid = await _create_notification(title="Old Notification")

    async with get_session() as session:
        from sqlalchemy import select, update

        stmt = (
            update(SystemNotification)
            .where(SystemNotification.id == nid)
            .values(
                is_read=True,
                created_at=datetime.now(timezone.utc) - timedelta(days=31),
            )
        )
        await session.execute(stmt)
        await session.commit()

    await cleanup_old_notifications()

    async with get_session() as session:
        result = await session.execute(select(SystemNotification).where(SystemNotification.id == nid))
        assert result.scalar_one_or_none() is None
