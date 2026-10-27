"""Every entry that can bind a workspace refuses a folder that contains protected locations."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from app.services.chat.chat_service import ChatService
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("files", preset="projects")

HOME = str(Path.home())


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


def _assert_refused(res: httpx.Response, *, field: str, issue: str) -> None:
    assert res.status_code == 400, res.text
    details = res.json().get("detail", res.json())["error"]["details"]
    assert {"field": field, "issue": issue} in details


async def _seed_chat(*, workspace_dir: str | None = None) -> str:
    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    chat_id = f"c-wspolicy-{uuid.uuid4().hex[:8]}"
    async with get_session_factory()() as db:
        db.add(Chat(id=chat_id, title="policy probe", action_mode="agent", source="web", workspace_dir=workspace_dir))
        await db.commit()
    return chat_id


@pytest.mark.asyncio
@pytest.mark.parametrize(("raw", "issue"), [(HOME, "too_broad"), ("/", "too_broad"), (f"{HOME}/.ssh", "dangerous")])
async def test_project_create_update_and_adopt_refuse_unsafe_folders(
    async_client: httpx.AsyncClient, raw: str, issue: str
) -> None:
    _assert_refused(
        await async_client.post("/api/v1/projects/", json={"name": "p", "workspace_path": raw}),
        field="workspace_path",
        issue=issue,
    )
    _assert_refused(
        await async_client.post("/api/v1/projects/adopt", json={"workspace_path": raw}),
        field="workspace_path",
        issue=issue,
    )
    project_id = (await async_client.post("/api/v1/projects/", json={"name": "q"})).json()["data"]["project"]["id"]
    _assert_refused(
        await async_client.put(f"/api/v1/projects/{project_id}", json={"workspace_path": raw}),
        field="workspace_path",
        issue=issue,
    )


@pytest.mark.asyncio
async def test_chat_workspace_patch_refuses_home_and_accepts_a_project_folder(
    async_client: httpx.AsyncClient, tmp_path: Path
) -> None:
    chat_id = await _seed_chat()

    _assert_refused(
        await async_client.patch(f"/api/v1/chats/{chat_id}/workspace", json={"workspace_dir": HOME}),
        field="workspace_dir",
        issue="too_broad",
    )
    _assert_refused(
        await async_client.patch(f"/api/v1/chats/{chat_id}/workspace", json={"workspace_dir": str(tmp_path / "gone")}),
        field="workspace_dir",
        issue="not_a_directory",
    )

    ok = await async_client.patch(f"/api/v1/chats/{chat_id}/workspace", json={"workspace_dir": str(tmp_path)})
    assert ok.status_code == 200, ok.text
    assert ok.json()["data"]["workspace_dir"] == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_a_stored_home_workspace_is_replaced_by_the_chat_sandbox_on_read(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = await _seed_chat(workspace_dir=HOME)

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    workspace_dir = res.json()["data"]["chat"]["workspace_dir"]
    assert workspace_dir != HOME
    assert chat_id in workspace_dir

    meta = await ChatService.get_chat_metadata(chat_id)
    assert meta is not None and meta.workspace_dir == workspace_dir


def _transcript(cwd: str) -> str:
    return "\n".join(
        json.dumps(entry)
        for entry in (
            {"role": "user", "content": "hello", "cwd": cwd},
            {"role": "assistant", "content": "hi there"},
        )
    )


async def _import(async_client: httpx.AsyncClient, cwd: str, **extra: str) -> httpx.Response:
    return await async_client.post("/api/v1/chats/import-transcript", json={"raw_content": _transcript(cwd), **extra})


@pytest.mark.asyncio
async def test_import_drops_an_untrusted_cwd_that_is_too_broad(async_client: httpx.AsyncClient) -> None:
    res = await _import(async_client, HOME)
    assert res.status_code == 200, res.text

    meta = await ChatService.get_chat_metadata(res.json()["chat_id"])
    assert meta is not None and meta.workspace_dir is None


@pytest.mark.asyncio
async def test_import_keeps_a_cwd_that_is_a_real_project_folder(async_client: httpx.AsyncClient, tmp_path: Path) -> None:
    res = await _import(async_client, str(tmp_path))
    assert res.status_code == 200, res.text

    meta = await ChatService.get_chat_metadata(res.json()["chat_id"])
    assert meta is not None and meta.workspace_dir == str(tmp_path.resolve())


@pytest.mark.asyncio
async def test_import_without_a_usable_cwd_does_not_invent_a_workspace(async_client: httpx.AsyncClient) -> None:
    res = await _import(async_client, "/no/such/place/on/this/machine")
    assert res.status_code == 200, res.text

    meta = await ChatService.get_chat_metadata(res.json()["chat_id"])
    assert meta is not None and meta.workspace_dir is None


@pytest.mark.asyncio
async def test_import_refuses_an_explicit_target_that_is_too_broad(async_client: httpx.AsyncClient) -> None:
    _assert_refused(await _import(async_client, "", target_workspace=HOME), field="target_workspace", issue="too_broad")
