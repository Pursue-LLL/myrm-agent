"""Chrome E2E: OpenCode Go provider — Settings model fetch + live chat reply."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import get_e2e_ui_url, wait_e2e_provider_ready  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    open_mcp_page_async,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once
from tests.support.test_secrets import resolve_test_env

E2E_PROMPT = "只回复 OK"
TURN_WAIT_SEC = 300.0
_EXPECTED_MODEL = "deepseek-v4-flash"
_WARM_ROUTE_TIMEOUT_SEC = 20.0

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_SETTINGS_MODELS_SHELL_STATE = """(() => {
  try {
    const bodyText = document.body?.innerText || '';
    return {
      ready:
        location.pathname.includes('/settings/models') &&
        bodyText.length > 20 &&
        !!document.querySelector('[data-testid="settings-layout"]'),
      pathname: location.pathname,
      bodyLength: bodyText.length,
    };
  } catch (err) {
    return {
      ready: false,
      pathname: location.pathname,
      bodyLength: 0,
      err: String(err),
    };
  }
})()"""


def _fetch_models_js(*, local_pool: bool) -> str:
    success_expr = (
        "text.includes('deepseek-v4-flash')"
        if local_pool
        else "text.includes('deepseek-v4-flash') && text.includes('minimax-m3')"
    )
    provider_checks = (
        "['OpenCode Go', 'OpenAI-Like', 'OpenAI', 'openai-like', 'Compatible', '兼容']" if local_pool else "['OpenCode Go']"
    )
    return f"""(async () => {{
  try {{
    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const providerLabels = Array.from(document.querySelectorAll('[aria-label]'))
      .map((el) => el.getAttribute('aria-label') || '')
      .filter((label) => label.length > 0);
    const patterns = {provider_checks};
    const provider = Array.from(document.querySelectorAll('[aria-label]')).find((el) => {{
      const label = el.getAttribute('aria-label') || '';
      return patterns.some((pattern) => label.includes(pattern));
    }});
    if (!provider) {{
      return {{
        ok: false,
        step: 'provider_not_found',
        providerLabels: providerLabels.slice(0, 16),
        pathname: location.pathname,
      }};
    }}
    provider.click();
    await sleep(800);
    const fetchBtn = Array.from(document.querySelectorAll('button')).find((btn) =>
      /获取模型|Get Models|Get models/i.test(btn.textContent || ''),
    );
    if (!fetchBtn) {{
      return {{
        ok: false,
        step: 'fetch_button_not_found',
        providerLabels: providerLabels.slice(0, 16),
        pathname: location.pathname,
      }};
    }}
    fetchBtn.click();
    for (let attempt = 0; attempt < 40; attempt += 1) {{
      await sleep(500);
      const text = document.body.innerText || '';
      if ({success_expr}) {{
        return {{ ok: true, step: 'models_loaded', attempt }};
      }}
      if (/apiFetchFailed|不支持获取模型|does not support fetching model/i.test(text)) {{
        return {{ ok: false, step: 'fetch_failed', snippet: text.slice(0, 400) }};
      }}
    }}
    return {{
      ok: false,
      step: 'timeout_waiting_models',
      snippet: (document.body.innerText || '').slice(0, 400),
    }};
  }} catch (err) {{
    return {{ ok: false, step: 'js_exception', err: String(err) }};
  }}
}})()"""


def _is_opencode_go_base_url(base_url: str) -> bool:
    """OpenCode Go direct zen endpoint or local dev pool proxy."""
    normalized = base_url.strip().lower()
    return "opencode.ai" in normalized or "localhost:20128" in normalized


def _require_opencode_go_config() -> None:
    base_url = resolve_test_env("BASIC_BASE_URL", "")
    api_key = resolve_test_env("BASIC_API_KEY", "")
    model = resolve_test_env("BASIC_MODEL", "")
    lite_model = resolve_test_env("LITE_MODEL", "")
    if not api_key or not _is_opencode_go_base_url(base_url):
        pytest.skip("OpenCode Go not configured in .env.test")
    if _EXPECTED_MODEL not in model and _EXPECTED_MODEL not in lite_model:
        pytest.skip(f"BASIC_MODEL or LITE_MODEL must include {_EXPECTED_MODEL} for this E2E")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_opencode_go_settings_fetch_models_dialog(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: Settings → OpenCode Go → 获取模型 → provider API list visible."""
    _require_opencode_go_config()
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)

    with open_settings_subroute("/settings/models") as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        state: dict[str, object] = {}
        for attempt in range(3):
            try:
                state = wait_for_state(
                    client,
                    page,
                    _SETTINGS_MODELS_SHELL_STATE,
                    timeout_sec=min(90.0, _warm_ui_parallel_wait_sec(45.0)),
                    page_url=f"{get_e2e_ui_url().rstrip('/')}/settings/models",
                    blank_heal_mode="direct",
                )
                if state.get("ready") is True:
                    break
            except (AssertionError, RuntimeError):
                if attempt >= 2:
                    raise
        assert state.get("ready") is True, state
        heartbeat_once()
        base_url = resolve_test_env("BASIC_BASE_URL", "")
        local_pool = "localhost:20128" in base_url.strip().lower()
        result = client.evaluate(
            page,
            _fetch_models_js(local_pool=local_pool),
            timeout_sec=120.0,
            await_promise=True,
        )
        assert isinstance(result, dict) and "ok" in result, result
        assert result.get("ok") is True, result


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_opencode_go_chat_reply_ok(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI chat using DB-configured OpenCode Go deepseek-v4-flash."""
    _require_opencode_go_config()
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/", timeout_sec=_warm_ui_parallel_wait_sec(30.0))

    session = await open_mcp_page_async(
        ui_base,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    )
    try:
        client = session.client
        page = session.page
        chat = McpChatSession(client, page)
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=120.0)
        await chat.click_new_chat()
        heartbeat_once()
        await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        state = await chat.wait_turn_done(E2E_PROMPT, timeout_sec=TURN_WAIT_SEC)
        if str(state.get("path", "")).startswith("/settings"):
            pytest.fail(f"Chat redirected to settings: {state}")
        assistant = str(state.get("assistantText") or state.get("lastAssistant") or state.get("lastAssistantSample") or "")
        has_ok = state.get("hasOk") is True
        assert has_ok or "OK" in assistant.upper(), (
            f"Expected OK reply (hasOk or text), assistant={assistant[:200]!r}, state={json.dumps(state)[:500]}"
        )
        chat_id = str(state.get("chatId") or "")
        if chat_id:
            e2e_resource_ledger.register("chat", chat_id)
    finally:
        await session.aclose()
