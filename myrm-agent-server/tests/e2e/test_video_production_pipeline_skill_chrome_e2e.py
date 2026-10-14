"""Real Chrome E2E: video-production-pipeline skill activation and execution via WebUI.

Simulates a real user interacting with the WebUI to invoke the video-production-pipeline skill
with the real configured LLM model, verifying the cinematic storyboard instruction and output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    ensure_e2e_yolo_mode,
    fetch_chat_messages,
    wait_e2e_provider_ready,
)
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import heartbeat_once  # noqa: E402

_LOGGER = logging.getLogger(__name__)

_SKILL_ID = "video-production-pipeline"


def _ensure_video_skill_enabled(api_url: str) -> None:
    try:
        http_json(
            "POST",
            f"{api_url}/api/v1/skills/test/ensure-prebuilt-catalog",
            expected_statuses=frozenset({200, 201, 404}),
        )
    except Exception:
        pass

    try:
        config = http_json("GET", f"{api_url}/api/v1/skills/config")
        if isinstance(config, dict):
            enabled = list(config.get("enabled_prebuilt_ids") or [])
            if _SKILL_ID not in enabled:
                enabled.append(_SKILL_ID)
                http_json(
                    "PUT",
                    f"{api_url}/api/v1/skills/config",
                    {"enabled_prebuilt_ids": enabled},
                )
    except Exception as exc:
        _LOGGER.warning("Could not ensure video skill in config: %s", exc)


_LAST_ASSISTANT_TEXT_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.();
  if (snap?.lastAssistantSample) {
    return { ready: true, text: String(snap.lastAssistantSample).trim(), via: 'bridge' };
  }
  const nodes = Array.from(document.querySelectorAll('[data-test-id="assistant-message"], [data-role="assistant"], .assistant-bubble'));
  if (nodes.length > 0) {
    const last = nodes[nodes.length - 1];
    return { ready: true, text: (last.textContent || "").trim(), via: 'dom' };
  }
  return { ready: false, text: "", via: 'none' };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
async def test_video_production_pipeline_skill_live_chrome_e2e() -> None:
    """A real user requests video production planning and cinematic storyboard through WebUI in real Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    ensure_e2e_yolo_mode(api_url=api_url)
    _ensure_video_skill_enabled(api_url)

    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready for live video skill E2E test")

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(client.new_page, ui_url, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(client.new_page, ui_url, timeout_ms=120_000)
        assert page is not None, "new_page returned no page"

        chat = McpChatSession(client, page)
        await chat.bootstrap(ui_url, timeout_sec=120.0)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(ui_url)

        # Pin basic model in WebUI bridge
        await chat.evaluate(
            """(async () => {
              const bridge = window.__MYRM_E2E_CHAT__;
              if (typeof bridge?.ensureProviders === 'function') {
                await bridge.ensureProviders();
              }
              if (typeof bridge?.pinBasicModelForE2e === 'function') {
                await bridge.pinBasicModelForE2e({ preserveActionMode: true });
              }
              return { ok: true };
            })()""",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )

        prompt = (
            "【视频分镜制作】我想制作一段15秒的产品宣传短视频，请按影视级分镜规范输出前两个分镜规划，必须包含景别与机位运镜描述。"
        )
        send_res = await chat.send_message(prompt, prompt, skip_model_sync=True)
        heartbeat_once()
        print(f"E2E_VIDEO_SKILL_SENT: {json.dumps(send_res, ensure_ascii=False)}", flush=True)

        chat_id = str(
            send_res.get("started", {}).get("chatId")
            or send_res.get("submit", {}).get("chatId")
            or (await chat.bridge_chat_id())
            or ""
        ).strip()

        after = await chat.wait_turn_settled(timeout_sec=240.0)
        print(f"E2E_VIDEO_SKILL_TURN_DONE: {json.dumps(after, ensure_ascii=False)}", flush=True)

        # 尝试从 UI 提取回复
        reply = await chat.evaluate(_LAST_ASSISTANT_TEXT_JS, intent=EvaluateIntent.SYNC_PROBE)
        assistant_text = ""
        if isinstance(reply, dict):
            assistant_text = str(reply.get("text", "")).strip()

        # 如果 UI 尚未渲染完毕或获取不到，从权威后端消息流获取
        if not assistant_text and chat_id:
            for _ in range(15):
                messages = fetch_chat_messages(chat_id, api_url=api_url)
                assistant_msgs = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
                if assistant_msgs:
                    assistant_text = str(assistant_msgs[-1].get("content") or "").strip()
                    if assistant_text:
                        break
                await asyncio.sleep(2.0)

        print(f"E2E_VIDEO_SKILL_ASSISTANT_REPLY: {assistant_text[:300]}", flush=True)
        assert len(assistant_text) >= 20, f"Assistant reply too short: {assistant_text}"
        has_storyboard_elements = any(
            kw in assistant_text for kw in ["分镜", "景别", "运镜", "画面", "特写", "镜头", "Shot", "Camera"]
        )
        assert has_storyboard_elements, f"Assistant reply missing storyboard elements: {assistant_text}"
    finally:
        try:
            if page:
                await asyncio.to_thread(client.close_page, page.id)
        except Exception:
            pass
        await asyncio.to_thread(client.close)
