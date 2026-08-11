"""LIVE product acceptance: extension browser_source + *.x.com policy + navigate X."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_memory_disabled,
    ensure_e2e_yolo_mode,
    wait_chat_messages_done,
    wait_e2e_backend_ready,
    wait_e2e_cdp_ready,
    wait_e2e_provider_ready,
    get_e2e_api_url,
)
from dev_gate_contract import EvaluateIntent  # noqa: E402
from e2e_live_flows._flow_base import FlowLogger  # noqa: E402
from e2e_live_flows.browser_takeover_live_gate import (  # noqa: E402
    ENABLE_BROWSER_JS,
    ENABLE_YOLO_JS,
)
from e2e_live_flows.browser_takeover_live_runner import (  # noqa: E402
    run_browser_takeover_live_session,
)
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import http_json  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402
from tests.support.extension_bridge_ws_stub import hold_extension_bridge_session  # noqa: E402

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

SET_EXTENSION_SOURCE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setBrowserSource) return { ok: false, err: 'no-setBrowserSource' };
  bridge.setBrowserSource('extension');
  return { ok: bridge.getBrowserSource?.() === 'extension', source: bridge.getBrowserSource?.() };
})()"""

X_PROMPT = (
    "产品验收：请用 browser 工具打开 https://x.com ，读取页面可见标题或首屏文案，"
    "用一句中文总结你看到了什么（登录页也算）。完成后只回复 DONE，不要调用其他工具。"
)


async def run_extension_x_product_flow(
    chat: McpChatSession,
    *,
    log: FlowLogger,
    ledger: E2EResourceLedger,
) -> str:
    del ledger
    api_url = get_e2e_api_url()

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")
    http_json(
        "PUT",
        f"{api_url}/api/v1/extension/access-policy",
        {
            "allow_all_eligible_tabs": True,
            "domains": ["*.x.com"],
            "paused_tab_ids": [],
        },
    )

    with hold_extension_bridge_session(api_url):
        status = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(status, dict)
        assert status.get("connected") is True
        assert status.get("access_policy_valid") is True
        hints = http_json("GET", f"{api_url}/api/v1/extension/setup-hints")
        assert isinstance(hints, dict)
        assert hints.get("access_policy_valid") is True
        log.emit(f"extension_ready relay_cdp_ready={hints.get('relay_cdp_ready')}")

        await chat.dismiss_modals()
        await chat.cdp("Page.navigate", {"url": f"{BASE_URL}/"}, recv_timeout=120.0)
        await asyncio.sleep(2.0)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
        await chat.ensure_model_ready(timeout_sec=180.0)

        source = await chat.evaluate(
            SET_EXTENSION_SOURCE_JS,
            intent=EvaluateIntent.SYNC_PROBE,
        )
        assert isinstance(source, dict) and source.get("ok") is True, source
        enabled = await chat.evaluate(
            ENABLE_BROWSER_JS,
            intent=EvaluateIntent.SYNC_PROBE,
        )
        assert isinstance(enabled, dict) and enabled.get("ok") is True, enabled
        await chat.evaluate(ENABLE_YOLO_JS, intent=EvaluateIntent.SYNC_PROBE)

        send_result = await chat.send_message(X_PROMPT, X_PROMPT)
        chat_id = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id:
            chat_id = str((await chat.bridge_chat_id()) or "").strip()
        log.emit(f"send_message chat_id={chat_id} mode={send_result.get('submit', {}).get('mode')}")
        assert chat_id
        assert send_result.get("submit", {}).get("mode") == "sendTurnSealed"

        done = await asyncio.to_thread(
            wait_chat_messages_done,
            chat_id,
            api_url=api_url,
            timeout_sec=300.0,
        )
        assert done is True, "Agent did not finish X.com product acceptance turn"
        return chat_id


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_live_extension_x_com_product_acceptance(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Extension + *.x.com policy: real model navigates x.com and completes."""
    if not wait_e2e_provider_ready():
        pytest.fail("Provider not ready — configure MiniMax in WebUI / .env.test")

    if not wait_e2e_cdp_ready(timeout_sec=45.0):
        pytest.fail("E2E Chrome CDP not ready — run ./myrm ready --chrome")

    ensure_e2e_yolo_mode()
    ensure_e2e_memory_disabled()
    if not wait_e2e_backend_ready(timeout_sec=90.0):
        pytest.fail("Backend not healthy before extension X LIVE acceptance")

    chat_id = await run_browser_takeover_live_session(
        ledger=e2e_resource_ledger,
        run_flow=run_extension_x_product_flow,
    )
    assert chat_id
