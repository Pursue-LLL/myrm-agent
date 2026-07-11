"""Chrome E2E test: Fork sandbox isolation via CDP + live API.

Validates the full user flow: fork from a sandbox-active chat,
verify child workspace resets to repo root, check UI navigation.

Prerequisites:
  - Chrome E2E running: ./myrm ready --chrome
  - Live server running on :8080 with frontend on :3000
  - A :3000 tab open in Chrome E2E
  - At least one chat with sandbox enabled (see conftest or manual setup)

Run: ./myrm ready --chrome && .venv/bin/python -m pytest tests/e2e/ -v --timeout=45
"""

import asyncio
import json
import urllib.request

import pytest

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8080"


def _chrome_page_ws() -> str | None:
    """Get Chrome CDP WebSocket URL for :3000 page."""
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:9333/json/list", timeout=3)
        pages = json.loads(resp.read())
    except Exception:
        return None

    target = next(
        (p for p in pages if "127.0.0.1:3000" in p["url"] and p.get("type") == "page"),
        None,
    )
    return target["webSocketDebuggerUrl"] if target else None


@pytest.fixture
def chrome_ws():
    """Provide Chrome CDP WebSocket or skip."""
    ws_url = _chrome_page_ws()
    if not ws_url:
        pytest.skip("Chrome E2E not available (port 9333 or :3000 page missing)")
    return ws_url


@pytest.fixture
def sandbox_parent_chat_id() -> str:
    """Find an existing chat with sandbox state in the live server.

    Iterates recent chats via detail API to find one whose workspace_dir
    contains 'sandbox'. Requires: at least one chat with sandbox enabled
    that has >=2 messages (for fork at index 1).
    """
    try:
        resp = urllib.request.urlopen(f"{API_URL}/api/v1/chats/?page=1&page_size=30", timeout=5)
        data = json.loads(resp.read())
    except Exception:
        pytest.skip("Live server :8080 not reachable")

    items = data.get("data", {}).get("items", [])
    for item in items:
        chat_id = item["id"]
        try:
            detail_resp = urllib.request.urlopen(
                f"{API_URL}/api/v1/chats/{chat_id}", timeout=3,
            )
            detail = json.loads(detail_resp.read())
            ws_dir = detail.get("data", {}).get("chat", {}).get("workspace_dir", "")
            if ws_dir and "sandbox" in ws_dir.lower():
                return chat_id
        except Exception:
            continue

    pytest.skip("No sandbox-active chat found in live DB")


@pytest.mark.asyncio
@pytest.mark.timeout(45)
async def test_fork_sandbox_isolation_chrome_e2e(
    chrome_ws: str, sandbox_parent_chat_id: str,
) -> None:
    """Fork from sandbox parent via Chrome CDP verifies workspace isolation.

    Tests:
    1. Fork API callable from real Chrome browser (via Next.js proxy)
    2. Fork-info returns correct parent relationship
    3. Forked chat navigable in UI
    4. Parent shows child in fork-info
    5. DB confirms sandbox isolation (workspace_dir reset to repo root)
    """
    import websockets

    chat_id = sandbox_parent_chat_id

    async with websockets.connect(chrome_ws, max_size=10**7) as ws:
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

        # Navigate to base to avoid relative URL issues
        await ev(f"window.location.href='{BASE_URL}/'")
        await asyncio.sleep(1)

        # T1: Fork
        fork = await ev(
            f"(async()=>{{const r=await fetch('{BASE_URL}/api/v1/chats/{chat_id}/fork',"
            f"{{method:'POST',headers:{{'Content-Type':'application/json'}},"
            f"body:JSON.stringify({{message_index:1}})}});return await r.json()}})()"
        )
        assert isinstance(fork, dict) and fork.get("success"), f"Fork failed: {fork}"
        new_id = fork["data"]["new_chat_id"]

        # T2: Fork-info
        info = await ev(
            f"(async()=>{{const r=await fetch('{BASE_URL}/api/v1/chats/{new_id}/fork-info');"
            f"return await r.json()}})()"
        )
        assert info["success"]
        assert info["data"]["parent_chat_id"] == chat_id

        # T3: Navigate to forked chat
        await ev(f"window.location.href='{BASE_URL}/c/{new_id}'")
        await asyncio.sleep(2)
        url = await ev("location.href")
        assert new_id in str(url)

        # T4: Parent shows child
        pinfo = await ev(
            f"(async()=>{{const r=await fetch('{BASE_URL}/api/v1/chats/{chat_id}/fork-info');"
            f"return await r.json()}})()"
        )
        assert pinfo["success"]
        assert any(c["chat_id"] == new_id for c in pinfo["data"]["children"])

    # T5: Verify sandbox isolation via live server API
    resp = urllib.request.urlopen(f"{API_URL}/api/v1/chats/{new_id}")
    child_data = json.loads(resp.read())
    child_chat = child_data["data"]["chat"]

    # Parent had sandbox active (workspace_dir pointed to sandbox worktree).
    # After fork, child must use repo root (sandbox_base_dir of parent), not the sandbox path.
    parent_resp = urllib.request.urlopen(f"{API_URL}/api/v1/chats/{chat_id}")
    parent_data = json.loads(parent_resp.read())
    parent_ws = parent_data["data"]["chat"]["workspace_dir"]

    child_ws = child_chat["workspace_dir"]
    assert child_ws != parent_ws, (
        f"Child should NOT inherit parent's sandbox workspace_dir ({parent_ws})"
    )
    assert "sandbox" not in child_ws.lower(), (
        f"Child workspace should not contain 'sandbox': {child_ws}"
    )
