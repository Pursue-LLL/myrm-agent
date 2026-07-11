"""Chrome E2E test: Fork sandbox isolation via CDP + live API.

Validates the full user flow: fork from a sandbox-active chat,
verify child workspace resets to repo root, check UI navigation.

Requires: Chrome E2E running on :9333 with a :3000 tab open.
Data setup uses ASGI transport (same as test_fork_api.py) to avoid
DB session isolation issues between pytest and live server.
"""

import asyncio
import json
import urllib.request
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport
from sqlalchemy import select

from app.database.models import Chat, Message
from app.platform_utils import get_session_factory
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="chats")


@pytest.fixture
def chrome_page_ws():
    """Get Chrome CDP WebSocket URL for :3000 page."""
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9333/json/list", timeout=3)
        pages = json.loads(resp.read())
    except Exception:
        pytest.skip("Chrome E2E not available (port 9333 unreachable)")

    target = next(
        (p for p in pages if "127.0.0.1:3000" in p["url"] and p.get("type") == "page"),
        None,
    )
    if not target:
        pytest.skip("No :3000 page open in Chrome E2E")
    return target["webSocketDebuggerUrl"]


@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_fork_sandbox_isolation_chrome_e2e(chrome_page_ws) -> None:
    """Fork from sandbox parent via Chrome CDP verifies workspace isolation.

    Tests:
    1. Fork API callable from real Chrome browser (via CDP)
    2. Fork-info returns correct parent
    3. Forked chat navigable in UI
    4. DB confirms sandbox isolation (workspace reset to repo root)
    """
    import websockets

    factory = get_session_factory()
    chat_id = f"e2e-fork-{uuid4().hex[:8]}"

    # Setup: create parent with sandbox + messages directly in shared DB
    async with factory() as db:
        db.add(Chat(
            id=chat_id,
            title="E2E Sandbox Fork",
            workspace_dir="/project/.sandboxes/sandbox-e2e",
            sandbox_base_dir="/project",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ))
        now = datetime.now(UTC)
        for i in range(3):
            db.add(Message(
                id=str(uuid4()), chat_id=chat_id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"E2E message {i}", sent_at=now, sent_timezone="UTC",
            ))
        await db.commit()

    # Connect to Chrome page via CDP
    async with websockets.connect(chrome_page_ws, max_size=10**7) as ws:
        mid = [0]

        async def ev(expr: str):
            mid[0] += 1
            await ws.send(json.dumps({
                "id": mid[0], "method": "Runtime.evaluate",
                "params": {"expression": expr, "returnByValue": True, "awaitPromise": True},
            }))
            while True:
                r = json.loads(await ws.recv())
                if r.get("id") == mid[0]:
                    res = r.get("result", {}).get("result", {})
                    return res.get("value") if res.get("value") is not None else res.get("description")

        # TEST 1: Fork via browser fetch (through Next.js proxy on :3000)
        fork = await ev(
            f"(async()=>{{const r=await fetch('/api/v1/chats/{chat_id}/fork',"
            f"{{method:'POST',headers:{{'Content-Type':'application/json'}},"
            f"body:JSON.stringify({{message_index:1}})}});return await r.json()}})()"
        )
        assert fork["success"], f"Fork API failed from Chrome: {fork}"
        new_id = fork["data"]["new_chat_id"]

        # TEST 2: Fork-info from browser confirms parent relationship
        info = await ev(
            f"(async()=>{{const r=await fetch('/api/v1/chats/{new_id}/fork-info');"
            f"return await r.json()}})()"
        )
        assert info["success"], f"Fork-info failed: {info}"
        assert info["data"]["parent_chat_id"] == chat_id

        # TEST 3: Navigate to forked chat in UI
        await ev(f"window.location.href='http://127.0.0.1:3000/c/{new_id}'")
        await asyncio.sleep(2)
        url = await ev("location.href")
        assert new_id in url, f"Navigation failed: {url}"

    # TEST 4: Verify sandbox isolation in DB
    async with factory() as db:
        child = (await db.execute(select(Chat).where(Chat.id == new_id))).scalar_one()
        assert child.workspace_dir == "/project", (
            f"Child workspace_dir should be repo root, got: {child.workspace_dir}"
        )
        assert child.sandbox_base_dir is None, (
            f"Child sandbox_base_dir should be None, got: {child.sandbox_base_dir}"
        )
