"""Chrome LIVE E2E: muse-spark Responses wire — 2-turn agent tool loop."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    open_mcp_page_async,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import upsert_provider
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

_MUSE_SPARK_MODEL = "muse-spark-1.2-contributor"
_PROVIDER_ID = "opencode_go"
_TURN_WAIT_SEC = 360.0

_TURN1_PROMPT = (
    "请必须使用 web_search 工具搜索「OpenCode AI」，用一句话总结搜索结果，"
    "并在最终回复末尾单独一行写 TOOL_LOOP_OK。"
)
_TURN2_PROMPT = "上一条你搜索到了什么？最终回复末尾单独一行写 TURN2_OK。"

_PREP_AGENT_TURN_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ready: false, err: 'no-bridge' };
  await bridge.ensureProviders?.();
  bridge.setActionMode?.('agent');
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  bridge.setSseCaptureMessageId?.(null);
  bridge.setCurrentBuiltinTools?.(['web_search']);
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  if (typeof bridge.pinBasicModelForE2e === 'function') {
    await bridge.pinBasicModelForE2e({ preserveActionMode: true });
  }
  if (typeof bridge.syncSearchServicesFromE2eApi === 'function') {
    await bridge.syncSearchServicesFromE2eApi();
  }
  const debug = bridge.debugProviderState?.() ?? null;
  const sendReady = bridge.isSendReady?.() === true;
  const hasInput = !!document.querySelector('[data-chat-input]');
  return {
    ready: hasInput && sendReady && !!debug?.selection,
    sendReady,
    hasInput,
    selection: debug?.selection ?? null,
  };
})()"""


def _load_opencode_go_credentials() -> tuple[str, str] | None:
    byok = Path.home() / ".cursor-byok/opencode-go.json"
    if byok.is_file():
        data = json.loads(byok.read_text())
        accounts = data.get("account_keys")
        if isinstance(accounts, dict):
            key = accounts.get("account-1")
            if key:
                return str(key), "https://opencode.ai/zen/go/v1"
    return None


def _require_muse_spark_e2e() -> tuple[str, str]:
    creds = _load_opencode_go_credentials()
    if creds is None:
        pytest.skip("OpenCode Go BYOK key not configured (~/.cursor-byok/opencode-go.json)")
    return creds


def _seed_muse_spark_provider(api_url: str, *, api_key: str, base_url: str) -> None:
    current = fetch_config_value("providers", api_url=api_url)
    providers = current.get("providers")
    provider_list = providers if isinstance(providers, list) else []
    provider_list = upsert_provider(
        [p for p in provider_list if isinstance(p, dict)],
        provider_id=_PROVIDER_ID,
        model_id=_MUSE_SPARK_MODEL,
        api_url=base_url,
        api_key=api_key,
    )
    dmc = dict(current.get("defaultModelConfig") or {})
    primary = {"providerId": _PROVIDER_ID, "model": _MUSE_SPARK_MODEL}
    dmc["baseModel"] = {
        "primary": primary,
        "fallback": None,
        "temperature": 0.7,
        "modelKwargs": {},
    }
    dmc["liteModel"] = {
        "primary": dict(primary),
        "fallback": None,
        "temperature": 0.7,
    }
    merged: dict[str, object] = {
        **current,
        "providers": provider_list,
        "defaultModelConfig": dmc,
        "customModelInfo": current.get("customModelInfo") or {},
    }
    put_config_value("providers", merged, api_url=api_url)


def _turn_has_marker(state: dict[str, object], marker: str) -> bool:
    assistant = str(
        state.get("assistantText") or state.get("lastAssistant") or state.get("lastAssistantSample") or ""
    )
    return marker in assistant.upper()


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="muse_spark_responses_wire",
)
@pytest.mark.integration
@pytest.mark.timeout(900)
@pytest.mark.asyncio
async def test_muse_spark_responses_wire_two_turn_tool_loop(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: muse-spark Turn1 web_search tool loop → Turn2 reasoning replay."""
    api_key, base_url = _require_muse_spark_e2e()
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    _seed_muse_spark_provider(api_base, api_key=api_key, base_url=base_url)

    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/", timeout_sec=30.0)

    session = await open_mcp_page_async(
        ui_base,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    )
    try:
        chat = McpChatSession(session.client, session.page)
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=120.0)
        prep = await chat.evaluate(_PREP_AGENT_TURN_JS, await_promise=True)
        assert isinstance(prep, dict) and prep.get("ready") is True, prep
        await chat.click_new_chat()
        heartbeat_once()

        await chat.send_message(_TURN1_PROMPT, _TURN1_PROMPT)
        turn1 = await chat.wait_turn_done(_TURN1_PROMPT, timeout_sec=_TURN_WAIT_SEC)
        if str(turn1.get("path", "")).startswith("/settings"):
            pytest.fail(f"Chat redirected to settings on turn 1: {turn1}")
        assert _turn_has_marker(turn1, "TOOL_LOOP_OK"), (
            f"Turn1 missing TOOL_LOOP_OK: {json.dumps(turn1, ensure_ascii=False)[:800]}"
        )

        heartbeat_once()
        await chat.send_message(_TURN2_PROMPT, _TURN2_PROMPT)
        turn2 = await chat.wait_turn_done(_TURN2_PROMPT, timeout_sec=_TURN_WAIT_SEC)
        if str(turn2.get("path", "")).startswith("/settings"):
            pytest.fail(f"Chat redirected to settings on turn 2: {turn2}")
        assert _turn_has_marker(turn2, "TURN2_OK"), (
            f"Turn2 missing TURN2_OK (reasoning replay may have failed): "
            f"{json.dumps(turn2, ensure_ascii=False)[:800]}"
        )

        chat_id = str(turn2.get("chatId") or turn1.get("chatId") or "")
        if chat_id:
            e2e_resource_ledger.register("chat", chat_id)
    finally:
        await session.aclose()
