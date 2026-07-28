"""GET /chats/{id} returns project-bound workspace_dir (SSOT with Agent converter)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("files", preset="projects")


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_get_chat_returns_project_workspace_when_bound(
    async_client: httpx.AsyncClient,
    tmp_path,
) -> None:
    vault = tmp_path / "obsidian-vault"
    vault.mkdir()

    project_resp = await async_client.post("/api/v1/projects/", json={"name": "SSOT Project"})
    assert project_resp.status_code == 200
    project_id = project_resp.json()["data"]["project"]["id"]

    bind_resp = await async_client.put(
        f"/api/v1/projects/{project_id}",
        json={"workspace_path": str(vault)},
    )
    assert bind_resp.status_code == 200

    chat_id = f"c-ssot-{uuid.uuid4().hex[:8]}"
    stale_jit = "/tmp/myrm_stale_jit_workspace_do_not_use"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="SSOT workspace probe",
                project_id=project_id,
                workspace_dir=stale_jit,
                action_mode="agent",
                source="web",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    workspace_dir = res.json()["data"]["chat"]["workspace_dir"]
    assert workspace_dir == str(vault.resolve())
    assert workspace_dir != stale_jit


@pytest.mark.asyncio
async def test_get_chat_jit_fallback_without_project_bind(
    async_client: httpx.AsyncClient,
) -> None:
    chat_id = f"c-ssot-jit-{uuid.uuid4().hex[:8]}"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title="JIT workspace probe",
                action_mode="agent",
                source="web",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    res = await async_client.get(f"/api/v1/chats/{chat_id}")
    assert res.status_code == 200, res.text
    workspace_dir = res.json()["data"]["chat"]["workspace_dir"]
    assert isinstance(workspace_dir, str) and len(workspace_dir) > 0


async def _seed_project_bound_chat(
    async_client: httpx.AsyncClient,
    tmp_path,
    *,
    chat_suffix: str,
    vault_name: str = "obsidian-vault",
) -> tuple[str, str, str]:
    vault = tmp_path / vault_name
    vault.mkdir()

    project_resp = await async_client.post("/api/v1/projects/", json={"name": f"SSOT {chat_suffix}"})
    assert project_resp.status_code == 200
    project_id = project_resp.json()["data"]["project"]["id"]

    bind_resp = await async_client.put(
        f"/api/v1/projects/{project_id}",
        json={"workspace_path": str(vault)},
    )
    assert bind_resp.status_code == 200

    chat_id = f"c-ssot-{chat_suffix}-{uuid.uuid4().hex[:8]}"
    stale_jit = "/tmp/myrm_stale_jit_workspace_do_not_use"

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        db.add(
            Chat(
                id=chat_id,
                title=f"SSOT probe {chat_suffix}",
                project_id=project_id,
                workspace_dir=stale_jit,
                action_mode="agent",
                source="web",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()

    return chat_id, str(vault.resolve()), stale_jit


@pytest.mark.asyncio
async def test_suggest_uses_project_workspace_when_bound(
    async_client: httpx.AsyncClient,
    tmp_path,
) -> None:
    chat_id, vault_path, _stale_jit = await _seed_project_bound_chat(
        async_client,
        tmp_path,
        chat_suffix="suggest",
    )
    weekly = Path(vault_path) / "Weekly.md"
    weekly.write_text("# weekly notes", encoding="utf-8")

    res = await async_client.get(
        "/api/v1/files/suggest",
        params={"chat_id": chat_id, "q": "Weekly"},
    )
    assert res.status_code == 200, res.text
    results = res.json()["data"]["results"]
    workspace_hits = [item for item in results if item.get("source") == "workspace"]
    assert any(item.get("basename") == "Weekly.md" for item in workspace_hits)


@pytest.mark.asyncio
async def test_browse_content_via_chat_id_uses_project_workspace(
    async_client: httpx.AsyncClient,
    tmp_path,
) -> None:
    chat_id, vault_path, _stale_jit = await _seed_project_bound_chat(
        async_client,
        tmp_path,
        chat_suffix="browse",
        vault_name="browse-vault",
    )
    note = Path(vault_path) / "Weekly.md"
    note.write_text("project vault content", encoding="utf-8")

    res = await async_client.get(
        "/api/v1/files/browse/content",
        params={"chat_id": chat_id, "path": "Weekly.md"},
    )
    assert res.status_code == 200, res.text
    assert "project vault content" in res.text


@pytest.mark.asyncio
async def test_patch_chat_workspace_rejected_when_project_bound(
    async_client: httpx.AsyncClient,
    tmp_path,
) -> None:
    chat_id, _vault_path, _stale_jit = await _seed_project_bound_chat(
        async_client,
        tmp_path,
        chat_suffix="patch",
    )

    res = await async_client.patch(
        f"/api/v1/chats/{chat_id}/workspace",
        json={"workspace_dir": "/tmp/should-not-apply"},
    )
    assert res.status_code == 409, res.text
