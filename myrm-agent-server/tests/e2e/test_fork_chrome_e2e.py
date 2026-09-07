"""Chrome E2E test: Fork sandbox isolation via MCP mux + live API.

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
import sys
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import get_e2e_api_url, get_e2e_ui_url  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger


@pytest.fixture
def chrome_page(
    _require_live_e2e_lease: None,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    client = ChromeMcpClient()
    client.start()
    try:
        page = client.new_page(f"{get_e2e_ui_url()}/", timeout_ms=15_000)
        yield client, page
    finally:
        client.close()


@pytest.fixture
def sandbox_parent_chat_id() -> str:
    """Find an existing chat with sandbox state in the live server, or enable sandbox on one."""
    api_url = get_e2e_api_url()
    try:
        resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
            f"{api_url}/api/v1/chats/?page=1&page_size=30",
            timeout=5,
        )
        data = json.loads(resp.read())
    except Exception:
        pytest.fail(f"Live E2E API not reachable at {api_url} — run via ./myrm test -m e2e")

    items = data.get("data", {}).get("items", [])
    candidate_chat_id: str | None = None
    for item in items:
        chat_id = item["id"]
        try:
            detail_resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
                f"{api_url}/api/v1/chats/{chat_id}",
                timeout=3,
            )
            detail = json.loads(detail_resp.read())
            chat_obj = detail.get("data", {}).get("chat", {})
            ws_dir = chat_obj.get("workspace_dir", "")
            if ws_dir and "sandbox" in ws_dir.lower():
                return chat_id
            if candidate_chat_id is None and len(chat_obj.get("messages", [])) >= 2:
                candidate_chat_id = chat_id
        except Exception:
            continue

    if candidate_chat_id:
        try:
            enable_req = urllib.request.Request(
                f"{api_url}/api/v1/chats/{candidate_chat_id}/sandbox/enable",
                method="POST",
            )
            with urllib.request.urlopen(enable_req, timeout=10) as en_resp:  # noqa: S310
                if en_resp.status == 200:
                    return candidate_chat_id
        except Exception:
            pass

    # If still not found, seed a chat with git repo workspace and enable sandbox
    seed_chat_id = f"e2e-sandbox-{uuid4().hex[:8]}"
    repo_root = str(Path(__file__).resolve().parents[4])
    create_payload = {
        "chat_id": seed_chat_id,
        "title": "E2E Sandbox Fixture",
        "workspace_dir": repo_root,
        "messages": [
            {
                "messageId": f"msg-1-{uuid4().hex[:6]}",
                "chatId": seed_chat_id,
                "role": "user",
                "content": "Initialize project in sandbox",
            },
            {
                "messageId": f"msg-2-{uuid4().hex[:6]}",
                "chatId": seed_chat_id,
                "role": "assistant",
                "content": "Sandbox project initialized successfully.",
            },
        ],
    }
    req = urllib.request.Request(
        f"{api_url}/api/v1/chats/",
        data=json.dumps(create_payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310
            if resp.status == 200:
                patch_req = urllib.request.Request(
                    f"{api_url}/api/v1/chats/{seed_chat_id}/workspace",
                    data=json.dumps({"workspace_dir": repo_root}).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="PATCH",
                )
                with urllib.request.urlopen(patch_req, timeout=5) as patch_resp:  # noqa: S310
                    assert patch_resp.status == 200

                en_req = urllib.request.Request(
                    f"{api_url}/api/v1/chats/{seed_chat_id}/sandbox/enable",
                    method="POST",
                )
                with urllib.request.urlopen(en_req, timeout=10) as en_resp:  # noqa: S310
                    if en_resp.status == 200:
                        return seed_chat_id
    except Exception as exc:
        pytest.fail(f"Failed to prepare sandbox chat fixture: {exc}")

    pytest.skip("No sandbox-active chat found in live DB")


@pytest.mark.asyncio
@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(180)
async def test_fork_sandbox_isolation_chrome_e2e(
    chrome_page: tuple[ChromeMcpClient, McpPage],
    sandbox_parent_chat_id: str,
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Fork from sandbox parent via Chrome MCP verifies workspace isolation.

    Tests:
    1. Fork API callable from real Chrome browser (via Next.js proxy)
    2. Fork-info returns correct parent relationship
    3. Forked chat navigable in UI
    4. Parent shows child in fork-info
    5. DB confirms sandbox isolation (workspace_dir reset to repo root)
    """
    chat_id = sandbox_parent_chat_id
    client, page = chrome_page
    ui_url = get_e2e_ui_url()
    api_url = get_e2e_api_url()

    async def ev(expr: str) -> object:
        return await asyncio.to_thread(
            client.evaluate,
            page,
            expr,
            timeout_sec=60.0,
        )

    await asyncio.to_thread(client.navigate, page, f"{ui_url}/", timeout_ms=15_000)

    custom_title = "[分支 @ 第2轮] E2E Fork Verification"
    fork = await ev(
        f"(async()=>{{const r=await fetch('{ui_url}/api/v1/chats/{chat_id}/fork',"
        f"{{method:'POST',headers:{{'Content-Type':'application/json'}},"
        f"body:JSON.stringify({{message_index:1,new_title:'{custom_title}'}})}});return await r.json()}})()"
    )
    assert isinstance(fork, dict) and fork.get("success"), f"Fork failed: {fork}"
    data = fork.get("data")
    assert isinstance(data, dict)
    new_id = str(data["new_chat_id"])
    e2e_resource_ledger.register("chat", new_id)

    info = await ev(f"(async()=>{{const r=await fetch('{ui_url}/api/v1/chats/{new_id}/fork-info');return await r.json()}})()")
    assert isinstance(info, dict) and info.get("success") is True
    info_data = info.get("data")
    assert isinstance(info_data, dict) and info_data.get("parent_chat_id") == chat_id
    assert info_data.get("root_chat_id") is not None
    assert isinstance(info_data.get("depth"), int) and info_data.get("depth") >= 1

    await asyncio.to_thread(
        client.navigate,
        page,
        f"{ui_url}/c/{new_id}",
        timeout_ms=15_000,
    )
    url = await ev("location.href")
    assert new_id in str(url)

    pinfo = await ev(f"(async()=>{{const r=await fetch('{ui_url}/api/v1/chats/{chat_id}/fork-info');return await r.json()}})()")
    assert isinstance(pinfo, dict) and pinfo.get("success") is True
    parent_info = pinfo.get("data")
    children = parent_info.get("children") if isinstance(parent_info, dict) else None
    assert isinstance(children, list)
    assert any(isinstance(child, dict) and child.get("chat_id") == new_id for child in children)

    # T5: Verify sandbox isolation via live server API
    resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
        f"{api_url}/api/v1/chats/{new_id}"
    )
    child_data = json.loads(resp.read())
    child_chat = child_data["data"]["chat"]
    assert child_chat.get("title") == custom_title, f"Expected title {custom_title}, got {child_chat.get('title')}"

    # Parent had sandbox active (workspace_dir pointed to sandbox worktree).
    # After fork, child must use repo root (sandbox_base_dir of parent), not the sandbox path.
    parent_resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback URL
        f"{api_url}/api/v1/chats/{chat_id}"
    )
    parent_data = json.loads(parent_resp.read())
    parent_ws = parent_data["data"]["chat"]["workspace_dir"]

    child_ws = child_chat["workspace_dir"]
    assert child_ws != parent_ws, f"Child should NOT inherit parent's sandbox workspace_dir ({parent_ws})"
    assert "sandbox" not in child_ws.lower(), f"Child workspace should not contain 'sandbox': {child_ws}"
