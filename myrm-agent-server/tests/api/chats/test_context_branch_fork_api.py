"""API tests for context branch snapshot fork."""

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
                title="Branch fork probe",
                action_mode="agent",
                source="web",
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_fork_context_branch_missing_snapshot_returns_400(
    async_client: httpx.AsyncClient,
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import myrm_agent_harness.runtime.context.context_branches as branches_module

    root = tmp_path / "persistent"
    root.mkdir()
    monkeypatch.setattr(branches_module, "PERSISTENT_ROOT", str(root))

    chat_id = f"test-branch-missing-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    branch_res = await async_client.post(
        f"/api/v1/chats/{chat_id}/context/branches",
        json={"snapshot_path": ".context/missing.jsonl", "label": "Missing"},
    )
    assert branch_res.status_code == 200, branch_res.text
    branch_id = branch_res.json()["data"]["branch_id"]

    fork_res = await async_client.post(
        f"/api/v1/chats/{chat_id}/context/branches/{branch_id}/fork",
    )
    assert fork_res.status_code == 400, fork_res.text
