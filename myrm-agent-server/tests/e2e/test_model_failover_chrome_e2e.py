"""Chrome E2E: base model auth failure → configured fallback → WebUI toast + progress + reply."""

from __future__ import annotations

import asyncio
import contextlib
import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_config_value,
    get_e2e_api_url,
    get_e2e_ui_url,
    put_config_value,
    wait_e2e_provider_ready,
)
from cdp_chat.ui import chat_id_from_path  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402
from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from tests.support.chrome_mcp_e2e import open_mcp_page_async
from tests.support.e2e_provider_seed import (
    NONEXISTENT_MODEL_ID,
    infer_provider_id,
    strip_provider_prefix,
    upsert_provider,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once
from tests.support.test_secrets import load_test_secrets

E2E_PROMPT = "只回复 OK"
TURN_WAIT_SEC = 300.0
# Model-not-found is a failoverable harness error (auth is permanent/non-failoverable),
# so corrupting the primary model id exercises the real auto-switch path.

_PIN_BASIC_PRIMARY_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinBasicModelForE2e) {
    return { ok: false, err: 'no pinBasicModelForE2e' };
  }
  const sel = await bridge.pinBasicModelForE2e();
  return { ok: true, selection: sel };
})()"""

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

_ASSISTANT_OK_JS = """(() => {
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


def _configure_failover_providers(api_url: str) -> dict[str, object]:
    secrets = load_test_secrets()
    basic_model = secrets.basic_model
    lite_model = secrets.lite_model
    assert basic_model and secrets.basic_api_key, "BASIC_* missing in .env.test"
    assert lite_model and secrets.lite_api_key, "LITE_* missing in .env.test"

    basic_provider_id = infer_provider_id(basic_model)
    basic_model_id = strip_provider_prefix(basic_model)
    lite_provider_id = infer_provider_id(lite_model)
    lite_model_id = strip_provider_prefix(lite_model)

    # Primary is corrupted with a nonexistent model id (failoverable MODEL_NOT_FOUND)
    # instead of an invalid API key, which harness classifies as permanent auth error
    # and intentionally does NOT auto-switch.
    primary_model_id = NONEXISTENT_MODEL_ID

    current = fetch_config_value("providers", api_url=api_url)
    providers = current.get("providers")
    provider_list = providers if isinstance(providers, list) else []

    provider_list = upsert_provider(
        [p for p in provider_list if isinstance(p, dict)],
        provider_id=basic_provider_id,
        model_id=primary_model_id,
        api_url=secrets.basic_base_url,
        api_key=secrets.basic_api_key,
    )
    provider_list = upsert_provider(
        provider_list,
        provider_id=lite_provider_id,
        model_id=lite_model_id,
        api_url=secrets.lite_base_url,
        api_key=secrets.lite_api_key,
        # BASIC_MODEL and LITE_MODEL share the same provider (openai-like) in the
        # current .env.test SSOT; merge instead of replace so the corrupt primary
        # stays in enabledModels while the real fallback model remains usable.
        merge_models=True,
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
        # PRIVATE runtimes are shared between parallel chrome_e2e sessions. A
        # peer's preflight seed can overwrite our corrupt primary between PUT
        # and the UI pin. Re-apply until the corrupt state is actually visible
        # (bounded), since the test asserts the failover path, not a race.
        seeded_state: dict[str, object] = {}
        for _attempt in range(3):
            merged = _configure_failover_providers(api_url)
            merged_providers = (
                merged.get("providers")
                if isinstance(merged.get("providers"), list)
                else []
            )
            merged_ol = next(
                (
                    p
                    for p in merged_providers
                    if isinstance(p, dict) and str(p.get("id")) == "openai-like"
                ),
                None,
            )
            print(
                "E2E_FAILOVER_MERGED: attempt=%s merged_ol_enabled=%s",
                _attempt + 1,
                json.dumps((merged_ol or {}).get("enabledModels")),
            )
            if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=30.0):
                pytest.fail("Provider readiness failed after failover seed")
            seeded_state = fetch_config_value("providers", api_url=api_url)
            seeded_dmc = seeded_state.get("defaultModelConfig") or {}
            seeded_bm = seeded_dmc.get("baseModel") or {}
            seeded_providers = (
                seeded_state.get("providers")
                if isinstance(seeded_state.get("providers"), list)
                else []
            )
            seeded_openai_like = next(
                (
                    p
                    for p in seeded_providers
                    if isinstance(p, dict) and str(p.get("id")) == "openai-like"
                ),
                None,
            )
            corrupt_visible = str(
                (seeded_bm.get("primary") or {}).get("model")
            ) == NONEXISTENT_MODEL_ID and NONEXISTENT_MODEL_ID in (
                (seeded_openai_like or {}).get("enabledModels") or []
            )
            print(
                "E2E_FAILOVER_SEED_VERIFY: attempt=%s primary=%s/%s openai_like_enabled=%s visible=%s",
                _attempt + 1,
                str((seeded_bm.get("primary") or {}).get("providerId")),
                str((seeded_bm.get("primary") or {}).get("model")),
                json.dumps((seeded_openai_like or {}).get("enabledModels")),
                corrupt_visible,
            )
            if corrupt_visible:
                break
        if not corrupt_visible:
            pytest.fail(
                "Failover corrupt seed never became visible (parallel seed overwrite)"
            )

        async def run_flow(chat: McpChatSession) -> None:
            ui_base = _base_url()
            await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
            await chat.click_new_chat()
            pin_raw = await chat.evaluate(
                _PIN_BASIC_PRIMARY_JS,
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
            pin_state = (
                pin_raw if isinstance(pin_raw, dict) else json.loads(str(pin_raw))
            )
            assert pin_state.get("ok") is True, pin_state
            selection = pin_state.get("selection")
            assert isinstance(selection, dict), pin_state
            assert str(selection.get("model") or "") == NONEXISTENT_MODEL_ID, pin_state
            send_result = await chat.send_message(
                E2E_PROMPT,
                E2E_PROMPT,
                skip_model_sync=True,
            )
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
            ), "Expected model_failover progress step in WebUI after primary model failure"
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

        page_session = await open_mcp_page_async(
            _base_url(),
            request_timeout_sec=180.0,
            timeout_ms=120_000,
        )
        try:
            await run_flow(McpChatSession(page_session.client, page_session.page))
        finally:
            await page_session.aclose()
    finally:
        if isinstance(backup, dict) and backup:
            put_config_value("providers", backup, api_url=api_url)
