"""Chrome E2E: base model auth failure → configured fallback → WebUI toast + progress + reply."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    fetch_config_value,
    get_e2e_api_url,
    get_e2e_ui_url,
    put_config_value,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate_contract import EvaluateIntent  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once
from tests.support.test_secrets import load_test_secrets

E2E_PROMPT = "只回复 OK"
TURN_WAIT_SEC = 300.0
# Model-not-found is a failoverable harness error (auth is permanent/non-failoverable),
# so corrupting the primary model id exercises the real auto-switch path.
_NONEXISTENT_MODEL_ID = "__e2e_nonexistent_model__"

_FAILOVER_STEP_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    const steps = (msg.progressSteps?.length ? msg.progressSteps : msg.metadata?.progressSteps) || [];
    for (const step of steps) {
      const key = String(step.step_key || '');
      if (key === 'model_failover' || key.startsWith('model_failover_')) {
        return {
          ready: true,
          step_key: key,
          items: step.items || [],
        };
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""

_ASISTANT_OK_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    const msg = msgs[i];
    if (msg.role !== 'assistant' && msg.type !== 'assistant') continue;
    const text = String(msg.content || msg.text || '').trim();
    if (text.includes('OK')) {
      return { ready: true, snippet: text.slice(0, 120) };
    }
    return { ready: false, msg_count: msgs.length, last_assistant: text.slice(0, 120) };
  }
  return { ready: false, msg_count: msgs.length };
})()"""


def _strip_provider_prefix(model: str) -> str:
    if "/" not in model:
        return model
    return model.split("/", 1)[1]


def _infer_provider_id(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "minimax"


def _upsert_provider(
    providers: list[dict[str, object]],
    *,
    provider_id: str,
    model_id: str,
    api_url: str,
    api_key: str,
) -> list[dict[str, object]]:
    entry = {
        "id": provider_id,
        "name": provider_id,
        "apiUrl": api_url.rstrip("/"),
        "apiKeys": [{"key": api_key, "isActive": True}],
        "enabledModels": [model_id],
        "availableModels": [model_id],
        "providerType": "minimax" if provider_id == "minimax" else "openai",
        "isEnabled": True,
        "enabled": True,
    }
    merged: list[dict[str, object]] = []
    replaced = False
    for item in providers:
        if not isinstance(item, dict):
            continue
        if str(item.get("id")) == provider_id:
            merged.append(entry)
            replaced = True
        else:
            merged.append(item)
    if not replaced:
        merged.append(entry)
    return merged


def _configure_failover_providers(
    api_url: str, *, corrupt_primary: bool
) -> dict[str, object]:
    secrets = load_test_secrets()
    basic_model = secrets.basic_model
    lite_model = secrets.lite_model
    assert basic_model and secrets.basic_api_key, "BASIC_* missing in .env.test"
    assert lite_model and secrets.lite_api_key, "LITE_* missing in .env.test"

    basic_provider_id = _infer_provider_id(basic_model)
    basic_model_id = _strip_provider_prefix(basic_model)
    lite_provider_id = _infer_provider_id(lite_model)
    lite_model_id = _strip_provider_prefix(lite_model)

    # Primary is corrupted with a nonexistent model id (failoverable MODEL_NOT_FOUND)
    # instead of an invalid API key, which harness classifies as permanent auth error
    # and intentionally does NOT auto-switch.
    primary_model_id = _NONEXISTENT_MODEL_ID if corrupt_primary else basic_model_id

    current = fetch_config_value("providers", api_url=api_url)
    providers = current.get("providers")
    provider_list = providers if isinstance(providers, list) else []

    provider_list = _upsert_provider(
        [p for p in provider_list if isinstance(p, dict)],
        provider_id=basic_provider_id,
        model_id=primary_model_id,
        api_url=secrets.basic_base_url,
        api_key=secrets.basic_api_key,
    )
    provider_list = _upsert_provider(
        provider_list,
        provider_id=lite_provider_id,
        model_id=lite_model_id,
        api_url=secrets.lite_base_url,
        api_key=secrets.lite_api_key,
    )

    base_primary = {"providerId": basic_provider_id, "model": primary_model_id}
    base_fallback = {"providerId": lite_provider_id, "model": lite_model_id}
    dmc = dict(current.get("defaultModelConfig") or {})
    dmc["baseModel"] = {
        "primary": base_primary,
        "fallback": base_fallback,
        "temperature": 0.7,
        "modelKwargs": {},
    }
    dmc["liteModel"] = {
        "primary": dict(base_fallback),
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
    return merged


def _base_url() -> str:
    return get_e2e_ui_url().rstrip("/")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_model_failover_primary_to_fallback(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Nonexistent primary model; WebUI chat must failover, show progress, and still reply OK."""
    api_url = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=120.0):
        pytest.fail(
            "Provider config not ready for live failover E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    backup = fetch_config_value("providers", api_url=api_url)
    try:
        _configure_failover_providers(api_url, corrupt_primary=True)
        if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=60.0):
            pytest.fail("Provider readiness failed after failover seed")

        async def run_flow(chat: McpChatSession) -> None:
            ui_base = _base_url()
            await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
            await chat.click_new_chat()
            send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
            chat_id = (
                str(
                    send_result.get("started", {}).get("chatId")
                    or send_result.get("submit", {}).get("chatId")
                    or ""
                ).strip()
                or None
            )

            async def _poll_failover_step() -> dict[str, object] | None:
                deadline = time.monotonic() + TURN_WAIT_SEC
                while time.monotonic() < deadline:
                    raw = await chat.evaluate(
                        _FAILOVER_STEP_JS,
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                    state = raw if isinstance(raw, dict) else json.loads(str(raw))
                    if state.get("ready") is True:
                        return state
                    await asyncio.sleep(0.5)
                return None

            failover_task = asyncio.create_task(_poll_failover_step())

            async def _wait_failover_and_ok() -> (
                tuple[dict[str, object], dict[str, object] | None]
            ):
                deadline = time.monotonic() + TURN_WAIT_SEC
                last_main: dict[str, object] = {}
                while time.monotonic() < deadline:
                    ok_raw = await chat.evaluate(
                        _ASSISTANT_OK_JS,
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                    ok_dict = (
                        ok_raw if isinstance(ok_raw, dict) else json.loads(str(ok_raw))
                    )
                    raw_failover = await chat.evaluate(
                        _FAILOVER_STEP_JS,
                        intent=EvaluateIntent.SYNC_PROBE,
                    )
                    failover_state = (
                        raw_failover
                        if isinstance(raw_failover, dict)
                        else json.loads(str(raw_failover))
                    )
                    bridge = await chat._bridge_turn_snapshot()
                    streaming = (
                        isinstance(bridge, dict) and bridge.get("isStreaming") is True
                    )
                    last_main = await chat.main_state(
                        E2E_PROMPT, intent=EvaluateIntent.BRIDGE_POLL
                    )
                    if (
                        ok_dict.get("ready") is True
                        and failover_state.get("ready") is True
                        and not streaming
                        and not last_main.get("sending")
                    ):
                        return last_main, failover_state
                    await asyncio.sleep(0.5)
                return last_main, None

            after_turn, failover_state_early = await _wait_failover_and_ok()
            if failover_state_early is None:
                failover_state_early = await failover_task
            else:
                failover_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await failover_task
            failover_state = failover_state_early
            if str(after_turn.get("path", "")).startswith("/settings"):
                pytest.fail(f"Send redirected to settings: {after_turn}")

            resolved_chat_id = chat_id
            if not resolved_chat_id:
                href = str(after_turn.get("url") or "")
                resolved_chat_id = chat_id_from_path(href.split("?", 1)[0])

            if resolved_chat_id:
                e2e_resource_ledger.register("chat", resolved_chat_id)
            heartbeat_once()

            assert (
                failover_state is not None
            ), "Expected model_failover progress step in WebUI after primary auth failure"
            step_key = str(failover_state.get("step_key") or "")
            assert step_key.startswith("model_failover"), failover_state

            ok_state = await chat.evaluate(
                _ASSISTANT_OK_JS,
                intent=EvaluateIntent.SYNC_PROBE,
            )
            ok_dict = (
                ok_state if isinstance(ok_state, dict) else json.loads(str(ok_state))
            )
            assert (
                ok_dict.get("ready") is True
            ), f"Expected assistant OK after fallback; state={ok_dict!r} failover={failover_state!r}"

        client = ChromeMcpClient(request_timeout_sec=180.0)
        await asyncio.to_thread(client.start)
        page: McpPage | None = None
        try:
            try:
                page = await asyncio.to_thread(
                    client.new_page,
                    _base_url(),
                    timeout_ms=120_000,
                )
            except TimeoutError:
                await asyncio.sleep(2.0)
                page = await asyncio.to_thread(
                    client.new_page,
                    _base_url(),
                    timeout_ms=120_000,
                )
            if page is None:
                raise RuntimeError("new_page returned no page")
            await run_flow(McpChatSession(client, page))
        finally:
            await asyncio.to_thread(client.close)
    finally:
        if isinstance(backup, dict) and backup:
            put_config_value("providers", backup, api_url=api_url)
