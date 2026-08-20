"""
Integration tests for session access roots API (grant and revoke endpoints).

[POS] Session directory access API integration tests. Validates POST (grant)
and PATCH (revoke) endpoints through the full HTTP router layer with minimal app.
"""

from __future__ import annotations

import os
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
    from datetime import datetime, timezone

    from app.database.models.chat import Chat
    from app.platform_utils import get_session_factory

    session_factory = get_session_factory()
    async with session_factory() as db:
        chat = Chat(
            id=chat_id,
            title=f"Test Chat {chat_id[:8]}",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            session_access_roots=[],
        )
        db.add(chat)
        await db.commit()


@pytest.mark.asyncio
async def test_session_access_roots_grant_and_revoke_api(
    async_client: httpx.AsyncClient,
    tmp_path,
) -> None:
    chat_id = f"test-grant-{uuid.uuid4().hex[:8]}"
    await _create_chat(chat_id)

    target_dir = tmp_path / "project-dir"
    target_dir.mkdir()
    real_path = os.path.realpath(str(target_dir))

    # 1. Grant endpoint POST
    grant_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/session-access-roots",
        json={"path": str(target_dir), "writable": True, "label": "Project Dir"},
    )
    assert grant_resp.status_code == 200
    grant_data = grant_resp.json().get("data", {})
    roots = grant_data.get("session_access_roots", [])
    assert len(roots) == 1
    assert roots[0]["path"] == real_path
    assert roots[0]["writable"] is True

    # 2. Duplicate grant idempotency check (returns existing grant without duplicates)
    grant_dup_resp = await async_client.post(
        f"/api/v1/chats/{chat_id}/session-access-roots",
        json={"path": str(target_dir), "writable": False, "label": "Updated Label"},
    )
    assert grant_dup_resp.status_code == 200
    roots_dup = grant_dup_resp.json().get("data", {}).get("session_access_roots", [])
    assert len(roots_dup) == 1
    assert roots_dup[0]["path"] == real_path
    assert roots_dup[0]["writable"] is True

    # 3. Non-existent chat 404 check
    bad_grant_resp = await async_client.post(
        "/api/v1/chats/non-existent-id/session-access-roots",
        json={"path": str(target_dir)},
    )
    assert bad_grant_resp.status_code == 404

    # 4. Revoke endpoint PATCH
    revoke_resp = await async_client.patch(
        f"/api/v1/chats/{chat_id}/session-access-roots",
        json={"path": str(target_dir)},
    )
    assert revoke_resp.status_code == 200
    revoke_data = revoke_resp.json().get("data", {})
    roots_after = revoke_data.get("session_access_roots", [])
    assert len(roots_after) == 0

    # 5. Revoke non-existent chat 404 check
    bad_revoke_resp = await async_client.patch(
        "/api/v1/chats/non-existent-id/session-access-roots",
        json={"path": str(target_dir)},
    )
    assert bad_revoke_resp.status_code == 404
