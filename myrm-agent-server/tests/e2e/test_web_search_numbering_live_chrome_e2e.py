"""Chrome LIVE E2E: web_search source numbers continue across turns and every citation binds by number.

Real fast-search turns in the WebUI, no mocks. Both questions are scoped to Bilibili videos with an explicit
``site:`` operator, which the engine answers from the keyless Bilibili API: the run exercises the real
tool-call -> sources SSE -> numbering -> inline citation chain without spending search-provider credits
(a search service must still be configured, it gates the tool).

Contract asserted on the real UI and on the persisted history:
* every source of a turn carries a unique number and the second turn continues after the first;
* every inline citation anchor of a message opens the source carrying its number;
* the persisted history carries the live numbers (the second row may be saved a moment after the turn
  settles, so the check waits up to 30 s for it);
* the same numbers and bindings come back after a full reload of the chat.

Both sends assert that the chat is still in fast mode and print the mode around the send.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
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

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_ui_url,
    guarded_urlopen,
    open_mcp_page_async,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402
from tests.support.test_secrets import resolve_test_env  # noqa: E402

_TURN_WAIT_SEC = 180.0
_PERSIST_WAIT_SEC = 30.0
_FIRST_PROMPT = (
    "请必须使用 web_search 工具搜索，query 参数逐字使用「Python 3.14 新特性 site:bilibili.com/video」，"
    "不要改写，也不要追加其他词。用一句话总结搜索结果，正文中用【1】标注引用来源，末尾单独一行写 SCOPE_ONE_OK。"
    "完成搜索后直接给出最终回答，禁止调用其他工具。"
)
_SECOND_PROMPT = (
    "请再次使用 web_search 工具搜索，query 参数逐字使用「Rust 异步编程 site:bilibili.com/video」，"
    "不要改写，也不要追加其他词。用一句话总结这次的搜索结果，正文中用工具结果里给出的来源编号标注引用"
    "（形如【n】，编号以工具结果为准，不要自己编号），末尾单独一行写 SCOPE_TWO_OK。"
    "完成搜索后直接给出最终回答，禁止调用其他工具。"
)

_PREP_FAST_SEARCH_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ready: false, err: 'no-bridge' };
  await bridge.ensureProviders?.();
  bridge.setWorkflowMode?.(false);
  bridge.setActionMode?.('fast');
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  bridge.setSseCaptureMessageId?.(null);
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  if (typeof bridge.pinLiteModelForE2e === 'function') {
    await bridge.pinLiteModelForE2e({ preserveActionMode: true });
  } else if (typeof bridge.pinBasicModelForE2e === 'function') {
    await bridge.pinBasicModelForE2e({ preserveActionMode: true });
  }
  bridge.setActionMode?.('fast');
  if (typeof bridge.syncSearchServicesFromE2eApi === 'function') {
    await bridge.syncSearchServicesFromE2eApi();
  }
  const debug = bridge.debugProviderState?.() ?? null;
  const search = bridge.debugSearchState?.() ?? null;
  const sendReady = bridge.isSendReady?.() === true;
  const hasInput = !!document.querySelector('[data-chat-input]');
  const mode = bridge.getActionMode?.() ?? null;
  return {
    ready: hasInput && sendReady && !!debug?.selection && mode === 'fast'
      && Number(search?.enabledCount ?? 0) > 0,
    sendReady,
    hasInput,
    actionMode: mode,
    searchEnabled: Number(search?.enabledCount ?? 0),
    selection: debug?.selection ?? null,
  };
})()"""

# What the page reports about the chat right now; read around every send to tell a mode flip from a stalled send.
_PAGE_PROBE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const store = window.__myrmChatStore?.getState?.();
  return {
    actionMode: bridge?.getActionMode?.() ?? null,
    sendReady: bridge?.isSendReady?.() ?? null,
    loading: Boolean(store?.loading || store?.isStreaming),
    messageCount: Array.isArray(store?.messages) ? store.messages.length : null,
  };
})()"""

# One row per assistant message: its numbered sources, the numeric citation anchors rendered inside the
# message element, and any fullwidth marker that stayed literal in the prose.
_CITATION_STATE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const assistants = (store?.messages ?? []).filter((m) => m?.role === 'assistant');
  const rows = assistants.map((message) => {
    const nodes = document.querySelectorAll(`[data-message-id="${message.messageId}"]`);
    const el = nodes.length > 0 ? nodes[nodes.length - 1] : null;
    const sources = Array.isArray(message.sources) ? message.sources : [];
    const anchors = Array.from(el ? el.querySelectorAll('a') : [])
      .filter((a) => /^\\d+$/.test((a.textContent || '').trim()))
      .map((a) => ({ num: Number((a.textContent || '').trim()), href: a.getAttribute('href') || '' }));
    return {
      messageId: message.messageId,
      mounted: Boolean(el),
      content: String(message.content || ''),
      sources: sources.map((s) => ({ index: s?.index ?? null, url: String(s?.url || '') })),
      anchors,
      literalMarkers: ((el ? el.textContent : '') || '').match(/【\\d+】/g) ?? [],
    };
  });
  return { loading: Boolean(store?.loading || store?.isStreaming), assistants: rows };
})()"""


def _ensure_search_services(api_url: str) -> None:
    """Configure the search service the tool is gated on, exactly as the settings page persists it."""
    current = fetch_config_value("searchServices", api_url=api_url)
    configs = current.get("searchServiceConfigs")
    if isinstance(configs, list) and configs:
        return
    item: dict[str, object] = {
        "id": f"e2e-search-{uuid.uuid4().hex[:8]}",
        "name": "E2E Search",
        "enabled": True,
        "priority": 1,
        "search_service": resolve_test_env("SEARCH_SERVICE", "tavily") or "tavily",
        "api_key": resolve_test_env("TAVILY_API_KEY") or resolve_test_env("SEARCH_API_KEY", "test-tavily-key"),
        "createdAt": int(time.time() * 1000),
    }
    put_config_value("searchServices", {"searchServiceConfigs": [item]}, api_url=api_url)


def _api(method: str, url: str, timeout: float = 30.0) -> tuple[int, str]:
    request = urllib.request.Request(url, method=method)
    try:
        with guarded_urlopen(request, timeout_sec=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _persisted_source_indexes(api_url: str, chat_id: str) -> list[list[int]]:
    """Source numbers per assistant message as the backend persisted them."""
    status, body = _api("GET", f"{api_url}/api/v1/chats/{chat_id}/messages?page=1&page_size=20", timeout=60.0)
    assert status == 200, body[:400]
    items = (json.loads(body).get("data") or {}).get("messages") or []
    rows: list[list[int]] = []
    for item in items:
        if item.get("role") != "assistant":
            continue
        sources = (item.get("metadata") or {}).get("sources") or []
        rows.append(sorted(int(source["index"]) for source in sources if isinstance(source, dict) and source.get("index")))
    return rows


def _source_numbers(row: dict[str, object]) -> list[int]:
    sources = row.get("sources")
    assert isinstance(sources, list), row
    return sorted(int(source["index"]) for source in sources)


def _assert_numbering_and_binding(state: dict[str, object]) -> None:
    rows = state.get("assistants")
    assert isinstance(rows, list) and len(rows) == 2, state
    first, second = rows
    first_numbers, second_numbers = _source_numbers(first), _source_numbers(second)
    assert first_numbers and second_numbers, state
    assert len(set(first_numbers)) == len(first_numbers), f"duplicate numbers in turn 1: {first_numbers}"
    assert len(set(second_numbers)) == len(second_numbers), f"duplicate numbers in turn 2: {second_numbers}"
    assert not set(first_numbers) & set(second_numbers), f"turn 2 reused turn 1 numbers: {first_numbers} {second_numbers}"
    assert min(second_numbers) > max(first_numbers), f"turn 2 did not continue turn 1: {first_numbers} {second_numbers}"

    url_by_number: dict[int, str] = {}
    for row in rows:
        for source in row["sources"]:
            url_by_number[int(source["index"])] = str(source["url"])
            assert "bilibili.com" in str(source["url"]), f"source outside the requested site: {source}"

    for row in rows:
        assert row["anchors"], f"no inline citation anchor rendered: {row}"
        assert not row["literalMarkers"], f"a fullwidth marker stayed literal: {row}"
        for anchor in row["anchors"]:
            assert anchor["num"] in url_by_number, f"anchor without a source: {anchor} {url_by_number}"
            assert anchor["href"] == url_by_number[anchor["num"]], f"anchor opens the wrong source: {anchor} {url_by_number}"


async def _wait_cited_messages(chat: McpChatSession, *, expected: int, timeout_sec: float) -> dict[str, object]:
    """Poll until ``expected`` assistant messages are mounted, settled, and each shows sources and anchors."""
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {}
    while asyncio.get_event_loop().time() < deadline:
        heartbeat_once()
        raw = await chat.evaluate(_CITATION_STATE_JS, await_promise=False)
        last = raw if isinstance(raw, dict) else {"raw": raw}
        rows = last.get("assistants")
        if (
            last.get("loading") is False
            and isinstance(rows, list)
            and len(rows) == expected
            and all(row["mounted"] and row["sources"] and row["anchors"] for row in rows)
        ):
            return last
        await asyncio.sleep(2.0)
    return last


async def _probe_page(chat: McpChatSession) -> dict[str, object]:
    """Action mode and send readiness as the page reports them.

    A page that cannot answer is reported instead of raised: this runs while a failure is being described,
    and the probe must not replace the failure it describes.
    """
    try:
        raw = await chat.evaluate(_PAGE_PROBE_JS, await_promise=False)
    except Exception as exc:
        return {"probeError": f"{type(exc).__name__}: {exc}"[:200]}
    return raw if isinstance(raw, dict) else {"raw": raw}


async def _send_fast_search_turn(chat: McpChatSession, prompt: str, *, chat_id_hint: str | None = None) -> None:
    """Send one turn after asserting the chat is in fast mode; report the page state around the send."""
    before = await _probe_page(chat)
    assert before.get("actionMode") == "fast", f"the chat was not in fast mode when the send started: {before}"
    try:
        await chat.send_message(prompt, prompt, skip_model_sync=True, chat_id_hint=chat_id_hint)
    except (RuntimeError, TimeoutError) as exc:
        message = f"send failed (page before: {before}, after: {await _probe_page(chat)}): {exc}"
        raise (TimeoutError if isinstance(exc, TimeoutError) else RuntimeError)(message) from exc
    after = await _probe_page(chat)
    print(f"E2E_NUMBERING_SEND: mode before={before.get('actionMode')} after={after.get('actionMode')}", flush=True)


async def _wait_persisted_source_indexes(api_url: str, chat_id: str, expected: list[list[int]]) -> list[list[int]]:
    """Poll the persisted source numbers until they equal ``expected`` or the wait runs out.

    The second assistant row can be saved a moment after the live state settles. The moment each row appears
    is printed, so a late row reads as a delay and a missing row as a failure.
    """
    started = time.monotonic()
    appeared_at: dict[int, float] = {}
    while True:
        persisted = _persisted_source_indexes(api_url, chat_id)
        elapsed = time.monotonic() - started
        for row_count in range(1, len(persisted) + 1):
            appeared_at.setdefault(row_count, elapsed)
        if persisted == expected or elapsed >= _PERSIST_WAIT_SEC:
            rows = ", ".join(f"row{count}@{at:.1f}s" for count, at in sorted(appeared_at.items())) or "no row yet"
            print(f"E2E_NUMBERING_PERSISTED: {rows}; matches_live={persisted == expected}; waited={elapsed:.1f}s", flush=True)
            return persisted
        heartbeat_once()
        await asyncio.sleep(1.0)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_fast_search_numbers_continue_and_bind_across_turns_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Lane-C: two site-scoped fast-search turns -> continued numbering -> number-bound citations -> reload."""
    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    seed_live_e2e_providers(api_base)
    _ensure_search_services(api_base)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed - run ./myrm-dev ready --chrome")

    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/", timeout_sec=90.0)
    session = await open_mcp_page_async(ui_base, timeout_ms=120_000, request_timeout_sec=180.0)
    chat_id = ""
    try:
        active_api_base = get_e2e_api_url()
        seed_live_e2e_providers(active_api_base)
        _ensure_search_services(active_api_base)
        chat = McpChatSession(session.client, session.page)
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
        prep = await chat.evaluate(_PREP_FAST_SEARCH_JS, await_promise=True)
        assert isinstance(prep, dict) and prep.get("ready") is True, prep
        await chat.click_new_chat()
        prep = await chat.evaluate(_PREP_FAST_SEARCH_JS, await_promise=True)
        assert isinstance(prep, dict) and prep.get("ready") is True, prep
        heartbeat_once()

        await _send_fast_search_turn(chat, _FIRST_PROMPT)
        first_turn = await chat.wait_turn_settled(timeout_sec=_TURN_WAIT_SEC)
        chat_id = str(first_turn.get("chatId") or "")
        assert chat_id, first_turn
        print(f"E2E_NUMBERING_TURN1: {json.dumps(first_turn, ensure_ascii=False)[:500]}", flush=True)

        await _send_fast_search_turn(chat, _SECOND_PROMPT, chat_id_hint=chat_id)
        second_turn = await chat.wait_turn_settled(chat_id_hint=chat_id, min_user_msgs=2, timeout_sec=_TURN_WAIT_SEC)
        print(f"E2E_NUMBERING_TURN2: {json.dumps(second_turn, ensure_ascii=False)[:500]}", flush=True)

        live_state = await _wait_cited_messages(chat, expected=2, timeout_sec=60.0)
        print(f"E2E_NUMBERING_LIVE_STATE: {json.dumps(live_state, ensure_ascii=False)}", flush=True)
        _assert_numbering_and_binding(live_state)
        live_numbers = [_source_numbers(row) for row in live_state["assistants"]]
        persisted = await _wait_persisted_source_indexes(active_api_base, chat_id, live_numbers)
        assert persisted == live_numbers, (
            f"persisted source numbers differ from the live ones: persisted={persisted} live={live_numbers}"
        )

        await chat.navigate_to_chat(chat_id, ui_base)
        reloaded = await _wait_cited_messages(chat, expected=2, timeout_sec=90.0)
        print(f"E2E_NUMBERING_RELOADED_STATE: {json.dumps(reloaded, ensure_ascii=False)}", flush=True)
        _assert_numbering_and_binding(reloaded)
        assert [_source_numbers(row) for row in reloaded["assistants"]] == live_numbers
    finally:
        if chat_id:
            _api("DELETE", f"{get_e2e_api_url()}/api/v1/chats/{chat_id}", timeout=30.0)
        await session.aclose()
