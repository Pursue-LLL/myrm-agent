"""Chrome E2E: OpenCode Go provider — Settings model fetch + live chat reply."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import get_e2e_ui_url, wait_e2e_provider_ready  # noqa: E402
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease
from tests.support.test_secrets import resolve_test_env

E2E_PROMPT = "只回复 OK"
TURN_WAIT_SEC = 300.0
_EXPECTED_MODEL = "deepseek-v4-flash"

_FETCH_MODELS_JS = """async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const provider = Array.from(document.querySelectorAll('[aria-label]')).find((el) =>
    (el.getAttribute('aria-label') || '').includes('OpenCode Go'),
  );
  if (!provider) {
    return { ok: false, step: 'provider_not_found' };
  }
  provider.click();
  await sleep(800);
  const fetchBtn = Array.from(document.querySelectorAll('button')).find((btn) =>
    /获取模型|Get Models|Get models/i.test(btn.textContent || ''),
  );
  if (!fetchBtn) {
    return { ok: false, step: 'fetch_button_not_found' };
  }
  fetchBtn.click();
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await sleep(500);
    const text = document.body.innerText || '';
    if (text.includes('deepseek-v4-flash') && text.includes('minimax-m3')) {
      return { ok: true, step: 'models_loaded', attempt };
    }
    if (/apiFetchFailed|不支持获取模型|does not support fetching model/i.test(text)) {
      return { ok: false, step: 'fetch_failed', snippet: text.slice(0, 400) };
    }
  }
  return { ok: false, step: 'timeout_waiting_models' };
}"""


def _require_opencode_go_config() -> None:
    base_url = resolve_test_env("BASIC_BASE_URL", "")
    api_key = resolve_test_env("BASIC_API_KEY", "")
    model = resolve_test_env("BASIC_MODEL", "")
    if not api_key or "opencode.ai" not in base_url:
        pytest.skip("OpenCode Go not configured in .env.test")
    if _EXPECTED_MODEL not in model:
        pytest.skip(f"BASIC_MODEL must include {_EXPECTED_MODEL} for this E2E")


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_opencode_go_settings_fetch_models_dialog(e2e_resource_ledger: E2EResourceLedger) -> None:
    """Real WebUI: Settings → OpenCode Go → 获取模型 → provider API list visible."""
    _require_opencode_go_config()
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    api_base = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    prepare_e2e_ui_session(api_base)

    warm_ui_route("/")
    warm_ui_route("/settings/models")
    settings_url = f"{ui_url}/settings/models"
    home_url = f"{ui_url}/"
    client = ChromeMcpClient(request_timeout_sec=180.0)
    client.start()
    try:
        page = client.new_page(home_url, timeout_ms=120_000)
        client.navigate(page, settings_url, timeout_ms=180_000)
        dismiss_blocking_modals(client, page, recover_url=settings_url)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=settings_url,
        )
        heartbeat_e2e_lease()
        result = client.evaluate(
            page,
            _FETCH_MODELS_JS,
            timeout_sec=120.0,
            await_promise=True,
        )
        assert isinstance(result, dict), result
        assert result.get("ok") is True, result
        e2e_resource_ledger.register("page", page.target_id or "settings-models")
    finally:
        client.close()


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_opencode_go_chat_reply_ok(e2e_resource_ledger: E2EResourceLedger) -> None:
    """Real WebUI chat using DB-configured OpenCode Go deepseek-v4-flash."""
    _require_opencode_go_config()
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/")

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page = await asyncio.to_thread(client.new_page, ui_base, timeout_ms=120_000)
        chat = McpChatSession(client, page)
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=120.0)
        await chat.click_new_chat()
        heartbeat_e2e_lease()
        await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        state = await chat.wait_turn_done(E2E_PROMPT, timeout_sec=TURN_WAIT_SEC)
        if str(state.get("path", "")).startswith("/settings"):
            pytest.fail(f"Chat redirected to settings: {state}")
        assistant = str(state.get("assistantText") or state.get("lastAssistant") or "")
        assert assistant.strip(), f"No assistant text in state: {json.dumps(state)[:500]}"
        assert "OK" in assistant.upper(), f"Expected OK in reply, got: {assistant[:200]!r}"
        chat_id = str(state.get("chatId") or "")
        if chat_id:
            e2e_resource_ledger.register("chat", chat_id)
    finally:
        await asyncio.to_thread(client.close)
