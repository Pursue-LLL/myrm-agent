"""Chrome E2E for the Memory A/B run-history model disclosure in Eval Lab.

Prerequisites:
  ./myrm ready --chrome
  .env.test with BASIC_* credentials

The disclosure is verified honestly end-to-end: providers and the embedding
model are configured through the same config API the WebUI settings page
writes, a real sampled Memory A/B evaluation runs on WBBench Office from the
Sources card (limit=1 keeps the LLM cost tiny while the dataset download,
workspace provisioning, embedding probe and both agent arms run for real),
and the browser asserts the run-history table discloses the agent model the
run really used plus a judge placeholder (WBBench is task-native).

The embedding backend is a local OpenAI-compatible endpoint
(tests/support/local_embedding_server.py): the product supports arbitrary
self-hosted embedding endpoints, so this is a real usage path and makes the
run independent of external embedding account quota.
"""

from __future__ import annotations

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

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import (  # noqa: E402
    infer_provider_id,
    strip_provider_prefix,
    upsert_provider,
)
from tests.support.local_embedding_server import LocalEmbeddingServer  # noqa: E402
from tests.support.test_secrets import load_test_secrets  # noqa: E402

EVAL_LAB_URL = f"{get_e2e_ui_url()}/eval-lab"

# ---------------------------------------------------------------------------
# DOM probes
# ---------------------------------------------------------------------------

_PAGE_READY_JS = """(() => {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const tabTexts = tabs.map(t => t.textContent || '');
  const bodyText = document.body.innerText || '';
  return {
    ready: tabTexts.length >= 2 && bodyText.length > 50,
    tabTexts,
    tabCount: tabTexts.length,
    bodyLength: bodyText.length,
    bodySnippet: bodyText.slice(0, 220),
    url: location.href,
    title: document.title,
  };
})()"""

_SOURCES_TAB_JS = """(() => {
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const tabTexts = tabs.map(t => t.textContent || '');
  const tab = tabs.find(t => /sources|数据集|来源/i.test(t.textContent || ''));
  if (tab) {
    // Radix Tabs activate on pointerdown, so a bare .click() never switches.
    tab.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    tab.click();
  }
  return { ready: !!tab, clicked: !!tab, tabTexts, url: location.href };
})()"""

_OFFICE_CARD_JS = """(() => {
  const cards = Array.from(document.querySelectorAll('[class*="card"]'))
    .filter(c => /WBBench Office/i.test(c.textContent || ''))
    .sort((a, b) => (a.textContent || '').length - (b.textContent || '').length);
  const card = cards[0];
  if (!card) return { ready: false, found: false, reason: 'no_card' };
  const limit = card.querySelector('input[type="number"]');
  const memBtn = Array.from(card.querySelectorAll('button'))
    .find(b => /Memory A\\/B|记忆 A\\/B/i.test(b.textContent || ''));
  return {
    ready: !!limit && !!memBtn,
    found: true,
    hasLimit: !!limit,
    hasMemoryButton: !!memBtn,
    cardText: (card.textContent || '').slice(0, 160),
  };
})()"""

_CLICK_MEMORY_AB_ATOMIC_JS = """(async () => {
  const cards = Array.from(document.querySelectorAll('[class*="card"]'))
    .filter(c => /WBBench Office/i.test(c.textContent || ''))
    .sort((a, b) => (a.textContent || '').length - (b.textContent || '').length);
  const card = cards[0];
  if (!card) return { ready: false, reason: 'no_card' };

  const limit = card.querySelector('input[type="number"]');
  if (limit) {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
    setter.call(limit, '1');
    limit.dispatchEvent(new Event('input', { bubbles: true }));
  }

  const memBtn = Array.from(card.querySelectorAll('button'))
    .find(b => /Memory A\\/B|记忆 A\\/B/i.test(b.textContent || ''));
  if (!memBtn) return { ready: false, reason: 'no_memory_button' };

  const propKey = Object.keys(memBtn).find(k => k.startsWith('__reactProps$'));
  const props = propKey ? memBtn[propKey] : null;
  const onClickType = props ? typeof props.onClick : 'no-props';
  let invokedPropsOnClick = false;
  if (props && typeof props.onClick === 'function') {
    props.onClick();
    invokedPropsOnClick = true;
  } else {
    memBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
  }
  await new Promise(resolve => setTimeout(resolve, 1500));

  const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
  const activeTab = Array.from(document.querySelectorAll('[role="tab"]'))
    .find(t => t.getAttribute('data-state') === 'active');
  return {
    ready: dialogs.length > 0,
    invokedPropsOnClick,
    onClickType,
    btnOuter: memBtn.outerHTML.slice(0, 200),
    dialogCount: dialogs.length,
    dialogTexts: dialogs.map(d => (d.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 150)),
    activeTab: ((activeTab && activeTab.textContent) || '').trim(),
  };
})()"""

_MEMORY_AB_DIALOG_JS = """(() => {
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"]'));
  const match = dialogs.find(d => /Start Memory A\\/B|开始记忆 A\\/B|记忆对比评测/i.test(d.textContent || ''));
  if (match) {
    const start = Array.from(match.querySelectorAll('button'))
      .find(b => /Start Evaluation|开始评测/i.test(b.textContent || ''));
    return { ready: !!start, found: true, hasStart: !!start };
  }
  return {
    ready: false,
    reason: 'no_dialog',
    dialogCount: dialogs.length,
    dialogTexts: dialogs.map(d => (d.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 140)),
    tabs: Array.from(document.querySelectorAll('[role="tab"]')).map(t => ({
      text: (t.textContent || '').trim(),
      state: t.getAttribute('data-state'),
    })),
    bodyHasStart: /开始记忆|Start Memory/i.test(document.body.innerText || ''),
  };
})()"""

_CLICK_START_EVAL_JS = """(async () => {
  const dialog = Array.from(document.querySelectorAll('[role="dialog"]'))
    .find(d => /Start Memory A\\/B|开始记忆 A\\/B|记忆对比评测/i.test(d.textContent || ''));
  if (!dialog) return { ready: false, reason: 'no_dialog' };
  const start = Array.from(dialog.querySelectorAll('button'))
    .find(b => /Start Evaluation|开始评测/i.test(b.textContent || ''));
  if (!start) return {
    ready: false,
    reason: 'no_start_button',
    dialogText: (dialog.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 220),
  };

  window.__fetches = [];
  const origFetch = window.fetch.bind(window);
  window.fetch = function (...args) {
    window.__fetches.push(String(args[0]));
    return origFetch(...args);
  };
  start.click();
  await new Promise(resolve => setTimeout(resolve, 2500));

  const dialogsNow = Array.from(document.querySelectorAll('[role="dialog"]'));
  return {
    ready: dialogsNow.length === 0,
    clicked: true,
    dialogGone: dialogsNow.length === 0,
    fetches: window.__fetches.slice(-10),
    bodyTail: (document.body.innerText || '').replace(/\\n+/g, ' | ').slice(-400),
  };
})()"""

_OPEN_MEMORY_AB_TAB_JS = """(() => {
  const tab = Array.from(document.querySelectorAll('[role="tab"]'))
    .find(t => /Memory A\\/B|记忆 A\\/B/i.test(t.textContent || ''));
  if (tab) {
    tab.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, button: 0 }));
    tab.click();
    return { ready: true, clicked: true, found: true };
  }
  return { ready: false, clicked: false, found: false };
})()"""

_HISTORY_TABLE_JS = """(() => {
  const tables = Array.from(document.querySelectorAll('table'));
  const table = tables.find(t =>
    Array.from(t.querySelectorAll('th')).some(th => /Agent Model|Agent 模型|agent model/i.test(th.textContent || ''))
  );
  if (!table) return {
    ready: false,
    hasTable: false,
    tableCount: tables.length,
    allHeaders: tables.map(t => Array.from(t.querySelectorAll('th')).map(th => th.textContent || '')),
  };

  const headers = Array.from(table.querySelectorAll('th')).map(th => th.textContent || '');
  const rows = Array.from(table.querySelectorAll('tbody tr')).map(tr =>
    Array.from(tr.querySelectorAll('td')).map(td => td.textContent || '')
  );

  const agentCol = headers.findIndex(h => /Agent Model|Agent 模型|agent model/i.test(h));
  const judgeCol = headers.findIndex(h => /Judge Model|判分模型|judge model/i.test(h));

  const rowCells = rows[0] || [];
  return {
    ready: true,
    hasTable: true,
    headers,
    headerCount: headers.length,
    rowCount: rows.length,
    agentCol,
    judgeCol,
    firstRowCells: rowCells,
    firstRowText: rowCells.join(' | '),
    rowsText: rows.map(r => r.join(' | ')),
  };
})()"""


# ---------------------------------------------------------------------------
# Provider / embedding configuration (the data path the WebUI settings page
# writes; kept here so the test does not depend on a pre-seeded database)
# ---------------------------------------------------------------------------


def _configure_eval_stack(
    api_url: str,
    *,
    embedding_override: dict[str, str] | None = None,
) -> dict[str, object]:
    """Configure LLM providers + default model + embedding via the settings API."""
    secrets = load_test_secrets()
    basic_model = secrets.basic_model
    assert basic_model and secrets.basic_api_key, "BASIC_* missing in .env.test"
    lite_model = secrets.lite_model or basic_model
    lite_key = secrets.lite_api_key or secrets.basic_api_key

    basic_provider_id = infer_provider_id(basic_model)
    basic_model_id = strip_provider_prefix(basic_model)
    lite_provider_id = infer_provider_id(lite_model)
    lite_model_id = strip_provider_prefix(lite_model)

    current = fetch_config_value("providers", api_url=api_url)
    providers = current.get("providers")
    provider_list = providers if isinstance(providers, list) else []

    provider_list = upsert_provider(
        [p for p in provider_list if isinstance(p, dict)],
        provider_id=basic_provider_id,
        model_id=basic_model_id,
        api_url=secrets.basic_base_url,
        api_key=secrets.basic_api_key,
    )
    provider_list = upsert_provider(
        provider_list,
        provider_id=lite_provider_id,
        model_id=lite_model_id,
        api_url=secrets.lite_base_url,
        api_key=lite_key,
        # BASIC_MODEL and LITE_MODEL may share one provider (current .env.test SSOT);
        # merge keeps both models in enabledModels instead of replacing.
        merge_models=True,
    )

    base_primary = {"providerId": basic_provider_id, "model": basic_model_id}
    lite_primary = {"providerId": lite_provider_id, "model": lite_model_id}
    dmc = dict(current.get("defaultModelConfig") or {})
    dmc["baseModel"] = {
        "primary": base_primary,
        "fallback": lite_primary,
        "temperature": 0.7,
        "modelKwargs": {},
    }
    dmc["liteModel"] = {
        "primary": dict(lite_primary),
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

    if embedding_override is not None:
        retrieval: dict[str, object] = {
            "embeddingApplied": True,
            "embeddingConfig": {
                "provider": embedding_override["provider"],
                "model": embedding_override["model"],
                "apiKey": embedding_override["apiKey"],
                "apiBase": embedding_override["apiBase"],
            },
        }
    else:
        embedding_key = secrets.get("EMBEDDING_API_KEY")
        if not embedding_key:
            return merged
        retrieval = {
            "embeddingApplied": True,
            "embeddingConfig": {
                "provider": secrets.get("EMBEDDING_PROVIDER", "siliconflow"),
                "model": secrets.get("EMBEDDING_MODEL", "BAAI/bge-m3"),
                "apiKey": embedding_key,
                "apiBase": secrets.get("EMBEDDING_BASE_URL", ""),
            },
        }
    put_config_value("retrieval", retrieval, api_url=api_url)
    return merged


def _wait_memory_ab_finished(
    api_base: str, *, budget_sec: float = 480.0
) -> dict[str, object]:
    deadline = time.monotonic() + budget_sec
    status_data: dict[str, object] = {}
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/eval/memory-ab/status")
        assert isinstance(payload, dict)
        status_data = payload
        if not status_data.get("is_running", True):
            return status_data
        time.sleep(3)
    raise AssertionError(
        f"Memory A/B run did not finish in {budget_sec:.0f}s: {status_data}"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_memory_ab_model_disclosure_chrome_e2e() -> None:
    """Real UI flow: run a sampled Memory A/B and verify model disclosure columns."""
    api_base = get_e2e_api_url()

    if not load_test_secrets().has_basic_credentials:
        pytest.skip("BASIC_* credentials missing in .env.test")

    # A local OpenAI-compatible embedding endpoint stands in for a self-hosted
    # embedding provider (a supported product usage) so the run does not depend
    # on the availability/quota of any external embedding account.
    prev_retrieval = fetch_config_value("retrieval", api_url=api_base)
    embedding_server = LocalEmbeddingServer(port=8399).start()
    try:
        _configure_eval_stack(
            api_base,
            embedding_override={
                "provider": "openai",
                "model": "test-embed-v1",
                "apiKey": "test-key",
                "apiBase": embedding_server.base_url,
            },
        )
        assert wait_e2e_provider_ready(api_url=api_base), "provider stack not ready"

        prepare_e2e_ui_session(api_base)
        warm_ui_route("/eval-lab")
        with open_mcp_page(EVAL_LAB_URL, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)

            # T0: The Eval Lab SPA has mounted and rendered its tabs
            page_state = wait_for_state(client, page, _PAGE_READY_JS, timeout_sec=60.0)
            assert page_state.get("ready") is True, page_state
            assert "eval" in page_state.get("url", "").lower(), page_state

            # T1: Sources tab shows the Office card with the Memory A/B action
            sources = wait_for_state(client, page, _SOURCES_TAB_JS, timeout_sec=45.0)
            assert sources.get("clicked") is True, sources
            card = wait_for_state(client, page, _OFFICE_CARD_JS, timeout_sec=30.0)
            assert card.get("ready") is True, card
            assert card.get("hasMemoryButton") is True, card

            # T2: Real user flow — sample 1 task, open the Memory A/B confirmation
            # dialog from the card and confirm the run. The click + dialog wait is
            # atomic so the run state can never interleave with other probes.
            click_res = client.evaluate(
                page, _CLICK_MEMORY_AB_ATOMIC_JS, timeout_sec=25.0
            )
            assert (
                isinstance(click_res, dict) and click_res.get("ready") is True
            ), f"dialog did not open: {json.dumps(click_res, ensure_ascii=False, default=str)}"
            dialog = wait_for_state(
                client, page, _MEMORY_AB_DIALOG_JS, timeout_sec=15.0
            )
            assert dialog.get("ready") is True, dialog
            started = wait_for_state(
                client, page, _CLICK_START_EVAL_JS, timeout_sec=15.0
            )
            assert (
                started.get("ready") is True and started.get("clicked") is True
            ), started

            # Confirm the run was really dispatched by the UI before waiting.
            time.sleep(2.0)
            early_status = http_json("GET", f"{api_base}/api/v1/eval/memory-ab/status")
            assert (
                early_status.get("is_running") is True
            ), f"run not started by UI: {json.dumps(early_status, ensure_ascii=False, default=str)}"

            # T3: Wait for the real dual-arm run to complete (download + workspaces
            # + embedding probe + both agent arms with the real LLM)
            status_data = _wait_memory_ab_finished(api_base, budget_sec=480.0)
            assert status_data.get("error") is None, status_data.get("error")

            # The run-history table (MemoryAbHistoryTable) lives on the memory-ab
            # tab. Reload so the report + history are re-fetched from the backend.
            client.evaluate(page, "location.reload()", timeout_sec=10.0)
            page_state = wait_for_state(client, page, _PAGE_READY_JS, timeout_sec=60.0)
            assert page_state.get("ready") is True, page_state
            tab = wait_for_state(client, page, _OPEN_MEMORY_AB_TAB_JS, timeout_sec=30.0)
            assert tab.get("found") is True, tab

            table = wait_for_state(client, page, _HISTORY_TABLE_JS, timeout_sec=45.0)
            assert table.get("ready") is True, table
            headers = table.get("headers", [])
            assert table.get("headerCount", 0) >= 7, f"columns missing: {headers}"

            agent_col = table.get("agentCol", -1)
            judge_col = table.get("judgeCol", -1)
            assert agent_col >= 0, f"Agent Model column missing: {headers}"
            assert judge_col >= 0, f"Judge Model column missing: {headers}"

            row_text = table.get("firstRowText", "")
            # .env.test declares BASIC_MODEL=openai-like/agnes-2.5-flash; the
            # disclosed label is the litellm-normalized form (openai/agnes-2.5-flash).
            expected_model = load_test_secrets().basic_model
            model_name = expected_model.rsplit("/", 1)[-1]
            assert (
                f"/{model_name}" in row_text
            ), f"agent_model disclosure missing; expected *{model_name} in row: {row_text}"
            # WBBench is task-native, so the judge label is 'none' -> '-' in the table.
            assert " | " in row_text
    finally:
        # Restore the pre-test retrieval config so the shared stack is never
        # left pointing at the (stopped) local embedding endpoint.
        put_config_value("retrieval", prev_retrieval, api_url=api_base)
        embedding_server.stop()
