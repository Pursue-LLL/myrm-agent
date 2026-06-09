"""
Tests for Project CRUD and chat assignment API endpoints.

[POS] Project management API integration tests. Validates CRUD operations,
chat assignment, batch operations, and error handling through the HTTP layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from httpx import ASGITransport

from app.database.models.chat import Chat
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="projects")
from app.platform_utils import get_session_factory

PREFIX = "/api/v1/projects"
CHATS_PREFIX = "/api/v1/chats"


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


async def _create_chat(chat_id: str) -> None:
    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Test Chat {chat_id[:8]}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(chat)
        await db.commit()


@pytest.mark.asyncio
async def test_create_project(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(f"{PREFIX}/", json={"name": "My Project", "color": "#ff7eb3"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project"]["name"] == "My Project"
    assert data["project"]["color"] == "#ff7eb3"
    assert data["project"]["id"]


@pytest.mark.asyncio
async def test_create_project_default_color(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(f"{PREFIX}/", json={"name": "Default Color"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["project"]["color"].startswith("#")


@pytest.mark.asyncio
async def test_create_project_invalid_color(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(f"{PREFIX}/", json={"name": "Bad Color", "color": "red"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_list_projects(async_client: httpx.AsyncClient) -> None:
    await async_client.post(f"{PREFIX}/", json={"name": "List Test"})
    resp = await async_client.get(f"{PREFIX}/")
    assert resp.status_code == 200
    projects = resp.json()["data"]["projects"]
    assert any(p["name"] == "List Test" for p in projects)


@pytest.mark.asyncio
async def test_update_project(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Before Update"})
    project_id = create_resp.json()["data"]["project"]["id"]

    resp = await async_client.put(f"{PREFIX}/{project_id}", json={"name": "After Update", "color": "#7afcb4"})
    assert resp.status_code == 200
    updated = resp.json()["data"]["project"]
    assert updated["name"] == "After Update"
    assert updated["color"] == "#7afcb4"


@pytest.mark.asyncio
async def test_update_project_not_found(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.put(f"{PREFIX}/nonexistent", json={"name": "Ghost"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_project(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "To Delete"})
    project_id = create_resp.json()["data"]["project"]["id"]

    resp = await async_client.delete(f"{PREFIX}/{project_id}")
    assert resp.status_code == 200

    list_resp = await async_client.get(f"{PREFIX}/")
    projects = list_resp.json()["data"]["projects"]
    assert not any(p["id"] == project_id for p in projects)


@pytest.mark.asyncio
async def test_delete_project_unassigns_chats(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Unassign Test"})
    project_id = create_resp.json()["data"]["project"]["id"]

    chat_id = f"c-test-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    await async_client.patch(f"{PREFIX}/chats/{chat_id}/project", json={"projectId": project_id})

    await async_client.delete(f"{PREFIX}/{project_id}")

    chats_resp = await async_client.get(f"{CHATS_PREFIX}/", params={"page": 1, "page_size": 100})
    items = chats_resp.json()["data"]["items"]
    chat = next((c for c in items if c["id"] == chat_id), None)
    assert chat is not None
    assert chat.get("projectId") is None


@pytest.mark.asyncio
async def test_move_chat_to_project(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Move Target"})
    project_id = create_resp.json()["data"]["project"]["id"]

    chat_id = f"c-test-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    resp = await async_client.patch(f"{PREFIX}/chats/{chat_id}/project", json={"projectId": project_id})
    assert resp.status_code == 200

    chats_resp = await async_client.get(f"{CHATS_PREFIX}/", params={"project_id": project_id})
    items = chats_resp.json()["data"]["items"]
    assert any(c["id"] == chat_id for c in items)


@pytest.mark.asyncio
async def test_unassign_chat_from_project(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Unassign Source"})
    project_id = create_resp.json()["data"]["project"]["id"]

    chat_id = f"c-test-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    await async_client.patch(f"{PREFIX}/chats/{chat_id}/project", json={"projectId": project_id})
    resp = await async_client.patch(f"{PREFIX}/chats/{chat_id}/project", json={"projectId": None})
    assert resp.status_code == 200

    chats_resp = await async_client.get(f"{CHATS_PREFIX}/", params={"page": 1, "page_size": 100, "unassigned": "true"})
    items = chats_resp.json()["data"]["items"]
    assert any(c["id"] == chat_id for c in items)


@pytest.mark.asyncio
async def test_batch_move_chats(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Batch Target"})
    project_id = create_resp.json()["data"]["project"]["id"]

    chat_ids = []
    for _ in range(3):
        cid = f"c-test-{uuid.uuid4().hex[:8]}"
        await _create_chat(cid)
        chat_ids.append(cid)

    resp = await async_client.post(
        f"{PREFIX}/chats/batch-move",
        json={"chatIds": chat_ids, "projectId": project_id},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["movedCount"] == 3


@pytest.mark.asyncio
async def test_project_filter_in_chats_api(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Filter Test"})
    project_id = create_resp.json()["data"]["project"]["id"]

    assigned_id = f"c-test-{uuid.uuid4().hex[:8]}"
    unassigned_id = f"c-test-{uuid.uuid4().hex[:8]}"
    await _create_chat(assigned_id)
    await _create_chat(unassigned_id)

    await async_client.patch(f"{PREFIX}/chats/{assigned_id}/project", json={"projectId": project_id})

    filtered = await async_client.get(f"{CHATS_PREFIX}/", params={"project_id": project_id})
    items = filtered.json()["data"]["items"]
    assert any(c["id"] == assigned_id for c in items)
    assert not any(c["id"] == unassigned_id for c in items)

    unassigned = await async_client.get(f"{CHATS_PREFIX}/", params={"unassigned": "true"})
    u_items = unassigned.json()["data"]["items"]
    assert any(c["id"] == unassigned_id for c in u_items)
    assert not any(c["id"] == assigned_id for c in u_items)


# ── Edge Cases ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_duplicate_project_names_allowed(async_client: httpx.AsyncClient) -> None:
    r1 = await async_client.post(f"{PREFIX}/", json={"name": "DupName", "color": "#7cb9ff"})
    r2 = await async_client.post(f"{PREFIX}/", json={"name": "DupName", "color": "#ff7eb3"})
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["data"]["project"]["id"] != r2.json()["data"]["project"]["id"]


@pytest.mark.asyncio
async def test_move_nonexistent_chat_returns_404(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Edge Proj"})
    project_id = create_resp.json()["data"]["project"]["id"]
    resp = await async_client.patch(f"{PREFIX}/chats/nonexistent-chat/project", json={"projectId": project_id})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_move_chat_to_nonexistent_project_returns_404(async_client: httpx.AsyncClient) -> None:
    chat_id = f"c-test-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    resp = await async_client.patch(f"{PREFIX}/chats/{chat_id}/project", json={"projectId": "nonexistent-proj"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_batch_move_empty_list_returns_422(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Batch Empty"})
    project_id = create_resp.json()["data"]["project"]["id"]
    resp = await async_client.post(f"{PREFIX}/chats/batch-move", json={"chatIds": [], "projectId": project_id})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_project_empty_name_returns_422(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(f"{PREFIX}/", json={"name": ""})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_project_name_max_length(async_client: httpx.AsyncClient) -> None:
    # SharedContext name = f"Project: {name}" has max_length=120,
    # so effective project name limit is 120 - len("Project: ") = 111
    resp = await async_client.post(f"{PREFIX}/", json={"name": "A" * 111})
    assert resp.status_code == 200

    resp_too_long = await async_client.post(f"{PREFIX}/", json={"name": "A" * 256})
    assert resp_too_long.status_code in (422, 500)


@pytest.mark.asyncio
async def test_delete_nonexistent_project_returns_404(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.delete(f"{PREFIX}/nonexistent-proj")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project_no_fields_returns_400(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "No Fields"})
    project_id = create_resp.json()["data"]["project"]["id"]
    resp = await async_client.put(f"{PREFIX}/{project_id}", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_sort_order_in_response(async_client: httpx.AsyncClient) -> None:
    await async_client.post(f"{PREFIX}/", json={"name": "Sort Order Test"})
    resp = await async_client.get(f"{PREFIX}/")
    projects = resp.json()["data"]["projects"]
    assert all("sortOrder" in p for p in projects)


@pytest.mark.asyncio
async def test_short_hex_color_accepted(async_client: httpx.AsyncClient) -> None:
    resp = await async_client.post(f"{PREFIX}/", json={"name": "Short Hex", "color": "#abc"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_projectid_visible_in_chat_list(async_client: httpx.AsyncClient) -> None:
    create_resp = await async_client.post(f"{PREFIX}/", json={"name": "Visible PID"})
    project_id = create_resp.json()["data"]["project"]["id"]

    chat_id = f"c-test-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)
    await async_client.patch(f"{PREFIX}/chats/{chat_id}/project", json={"projectId": project_id})

    resp = await async_client.get(f"{CHATS_PREFIX}/", params={"project_id": project_id})
    items = resp.json()["data"]["items"]
    chat = next((c for c in items if c["id"] == chat_id), None)
    assert chat is not None
    assert chat["projectId"] == project_id
