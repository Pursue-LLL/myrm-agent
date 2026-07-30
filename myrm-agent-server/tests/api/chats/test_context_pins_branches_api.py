"""API tests for context pins and snapshot branch manifest endpoints."""

from __future__ import annotations

import uuid

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


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
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="Context pins/branches probe",
                action_mode="agent",
                source="web",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_context_pins_roundtrip(
    async_client: httpx.AsyncClient,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import myrm_agent_harness.runtime.context.session_context_pins as pins_module

    monkeypatch.setattr(pins_module, "PERSISTENT_ROOT", str(tmp_path))

    chat_id = f"test-pins-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    put_res = await async_client.put(
        f"/api/v1/chats/{chat_id}/context/pins",
        json={"files": ["src/auth/login.py", "src/auth/oauth.py"]},
    )
    assert put_res.status_code == 200, put_res.text
    put_payload = put_res.json()["data"]
    assert put_payload["files"] == ["src/auth/login.py", "src/auth/oauth.py"]

    get_res = await async_client.get(f"/api/v1/chats/{chat_id}/context/pins")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["data"]["files"] == ["src/auth/login.py", "src/auth/oauth.py"]


@pytest.mark.asyncio
async def test_context_branches_append_and_list(
    async_client: httpx.AsyncClient,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import myrm_agent_harness.runtime.context.context_branches as branches_module

    monkeypatch.setattr(branches_module, "PERSISTENT_ROOT", str(tmp_path))

    chat_id = f"test-branches-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    post_res = await async_client.post(
        f"/api/v1/chats/{chat_id}/context/branches",
        json={"snapshot_path": ".context/snap-1.jsonl", "label": "Before refactor"},
    )
    assert post_res.status_code == 200, post_res.text
    created = post_res.json()["data"]
    assert created["snapshot_path"] == ".context/snap-1.jsonl"
    assert created["label"] == "Before refactor"

    list_res = await async_client.get(f"/api/v1/chats/{chat_id}/context/branches")
    assert list_res.status_code == 200, list_res.text
    branches = list_res.json()["data"]["branches"]
    assert len(branches) == 1
    assert branches[0]["branch_id"] == created["branch_id"]


@pytest.mark.asyncio
async def test_context_pins_not_found_chat(async_client: httpx.AsyncClient) -> None:
    missing_id = f"missing-{uuid.uuid4().hex[:8]}"
    res = await async_client.get(f"/api/v1/chats/{missing_id}/context/pins")
    assert res.status_code == 404
