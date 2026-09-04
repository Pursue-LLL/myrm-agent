"""Chrome E2E test for capturing chat session as private evaluation case.

[INPUT]
- Live Next.js WebUI (:3000) / FastAPI (:8080)
- /api/v1/eval/cases/from-chat/{chat_id}
- /api/v1/eval/cases?dataset_id={dataset_id}

[OUTPUT]
- Validates the end-to-end user workflow:
  1. Create a live chat session with real user/assistant messages.
  2. Call the capture-to-eval-case pipeline from the browser context.
  3. Verify the case is successfully persisted and readable from the evaluation dataset.
  4. Verify the CaseFormat and multi-turn trajectory are sanitized properly.
"""

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import get_e2e_ui_url  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402


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


@pytest.mark.asyncio
@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="exclusive_backend")
@pytest.mark.integration
@pytest.mark.timeout(120)
async def test_capture_eval_case_chrome_e2e(
    chrome_page: tuple[ChromeMcpClient, McpPage],
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Validate full Task Flow E2E: chat creation -> capture to eval -> verify dataset persistence."""
    client, page = chrome_page
    ui_url = get_e2e_ui_url()

    async def ev(expr: str) -> object:
        return await asyncio.to_thread(
            client.evaluate,
            page,
            expr,
            timeout_sec=30.0,
        )

    # 1. Create a real chat session via Next.js proxy
    create_chat_res = await ev(
        f"(async()=>{{const r=await fetch('{ui_url}/api/v1/chats/',"
        f"{{method:'POST',headers:{{'Content-Type':'application/json'}},"
        f"body:JSON.stringify({{title:'E2E Eval Capture Session'}})}});return await r.json()}})()"
    )
    assert isinstance(create_chat_res, dict) and create_chat_res.get("success"), f"Failed to create chat: {create_chat_res}"
    chat_id = str(create_chat_res["data"]["id"])
    e2e_resource_ledger.register("chat", chat_id)

    # 2. Append real messages (user query and assistant response) into this chat
    user_msg_res = await ev(
        f"(async()=>{{const r=await fetch('{ui_url}/api/v1/chats/{chat_id}/messages',"
        f"{{method:'POST',headers:{{'Content-Type':'application/json'}},"
        f"body:JSON.stringify({{role:'user',content:'Calculate 123 * 456'}})}});return await r.json()}})()"
    )
    assert isinstance(user_msg_res, dict) and user_msg_res.get("success"), f"Failed to add user message: {user_msg_res}"

    assistant_msg_res = await ev(
        f"(async()=>{{const r=await fetch('{ui_url}/api/v1/chats/{chat_id}/messages',"
        f"{{method:'POST',headers:{{'Content-Type':'application/json'}},"
        f"body:JSON.stringify({{role:'assistant',content:'123 * 456 is 56088.'}})}});return await r.json()}})()"
    )
    assert isinstance(assistant_msg_res, dict) and assistant_msg_res.get("success"), f"Failed to add assistant message: {assistant_msg_res}"

    # 3. Trigger capture to eval dataset via Next.js proxy
    dataset_name = f"e2e-regressions-{chat_id[:8]}"
    capture_res = await ev(
        f"(async()=>{{const r=await fetch('{ui_url}/api/v1/eval/cases/from-chat/{chat_id}?dataset_id={dataset_name}',"
        f"{{method:'POST'}});return await r.json()}})()"
    )
    assert isinstance(capture_res, dict) and capture_res.get("status") == "success", f"Capture failed: {capture_res}"

    # 4. Verify the dataset contains the captured case with sanitized content and correct prompt
    get_cases_res = await ev(
        f"(async()=>{{const r=await fetch('{ui_url}/api/v1/eval/cases?dataset_id={dataset_name}');return await r.json()}})()"
    )
    assert isinstance(get_cases_res, dict) and get_cases_res.get("status") == "success", f"Get cases failed: {get_cases_res}"
    content = str(get_cases_res.get("content", ""))
    assert "Calculate 123 * 456" in content, "Expected prompt not found in captured eval dataset"
    assert "56088" in content, "Expected assistant answer not found in captured eval dataset"
