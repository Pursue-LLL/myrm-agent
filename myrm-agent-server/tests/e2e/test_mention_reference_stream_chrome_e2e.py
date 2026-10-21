"""Chrome LIVE E2E: real agent-stream request body carries correctly-filtered mention references.

Covers the messageRequest.ts `isReferenceTokenAlive` + `@wiki:` inline parsing fixes:
- kept reference: `@chat:Alpha` selected and left in the composer must still reach the
  agent-stream `mention_references` payload as `prior_chat`;
- zombie reference: the same selected reference, once its text is wiped from the composer,
  must NOT leak into the payload;
- inline `@wiki:` paste: a plain `@wiki:concept` token must be parsed into a `wiki_concept`
  reference with `concept_name`.

Request bodies are captured by wrapping `window.fetch` (no product-logic mock) and turns
are sent through the real E2E bridge (live profile).
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)


def _seed_prior_chat_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-prior-chat-fixture")
    assert isinstance(seeded, dict)
    composer_chat_id = str(seeded.get("composer_chat_id") or "")
    assert composer_chat_id.startswith("e2ecomp")
    return seeded


_FETCH_HOOK_JS = """(() => {
  window.__MYRM_STREAM_CAPTURE__ = [];
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    try {
      const input = args[0];
      const url = typeof input === 'string' ? input : input?.url || '';
      if (url.includes('/agents/agent-stream')) {
        const init = args[1];
        const rawBody = init && typeof init === 'object' ? init.body : null;
        if (typeof rawBody === 'string' && rawBody.trim()) {
          window.__MYRM_STREAM_CAPTURE__.push({
            url,
            body: JSON.parse(rawBody),
          });
        }
      }
    } catch {
      // ignore capture failures — assertion will fail on empty capture
    }
    return response;
  };
  return { hooked: true };
})()"""

_COMPOSER_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-chat-input]') && !!window.__MYRM_E2E_CHAT__,
  hasInput: !!document.querySelector('[data-chat-input]'),
  hasBridge: !!window.__MYRM_E2E_CHAT__,
}))()"""

_MENTION_ALPHA_ITEM_READY_JS = """(() => {
  const items = Array.from(document.querySelectorAll('[data-mention-item]'));
  const match = items.find((item) => (item.textContent || '').includes('Alpha'));
  return {
    ready: Boolean(match),
    itemText: (match?.textContent || '').slice(0, 120),
    count: items.length,
  };
})()"""

_CLICK_MENTION_ALPHA_ITEM_JS = """(() => {
  const items = Array.from(document.querySelectorAll('[data-mention-item]'));
  const match = items.find((item) => (item.textContent || '').includes('Alpha'));
  if (!match) return { ok: false, reason: 'no-alpha-mention-item', count: items.length };
  match.click();
  return { ok: true };
})()"""

_INPUT_VALUE_JS = """(() => {
  const el = document.querySelector('[data-chat-input]');
  return { ok: Boolean(el), value: el?.value ?? '' };
})()"""

_MENTION_CHIP_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const mentions = Array.isArray(store?.mentionReferences) ? store.mentionReferences : [];
  const priorMention = mentions.find((m) => m?.type === 'prior_chat');
  return {
    ready: Boolean(priorMention),
    mentionTypes: mentions.map((m) => m?.type),
    priorLabel: String(priorMention?.label || '').slice(0, 120),
  };
})()"""

_CAPTURE_FILTERED_JS = """(() => {
  const capture = window.__MYRM_STREAM_CAPTURE__ || [];
  const body = capture.length > 0 ? capture[capture.length - 1]?.body ?? null : null;
  const refs = body && Array.isArray(body.mention_references) ? body.mention_references : [];
  const agents = body && Array.isArray(body.mentioned_agent_ids) ? body.mentioned_agent_ids : [];
  const hasPriorChat = refs.some((r) => r?.type === 'prior_chat');
  const hasWiki = refs.some((r) => r?.type === 'wiki_concept');
  return {
    ready: capture.length > 0,
    hasPriorChat,
    hasWiki,
    refs,
    agents,
    userText: typeof body?.content === 'string' ? body.content : null,
  };
})()"""

_TURN_IDLE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {};
  return { ready: !snap.isStreaming };
})()"""


def _type_react_controlled_text(
    client: object,
    page: object,
    text: str,
) -> dict[str, object]:
    result = client.evaluate(  # type: ignore[attr-defined]
        page,
        f"""(() => {{
  const el = document.querySelector('[data-chat-input]');
  if (!el) return {{ ok: false, err: 'input-not-found' }};
  const proto = el instanceof HTMLTextAreaElement
    ? window.HTMLTextAreaElement.prototype
    : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {json.dumps(text)});
  const len = el.value.length;
  el.setSelectionRange(len, len);
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ ok: true, value: el.value }};
}})()""",
        timeout_sec=10.0,
    )
    assert isinstance(result, dict) and result.get("ok") is True, result
    return result


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_kept_prior_chat_mention_reaches_real_stream_payload() -> None:
    """Selecting @chat:Alpha and keeping its token must include prior_chat in the real payload."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_prior_chat_fixture(api_url)
    composer_path = str(seeded.get("ui_path") or f"/{seeded['composer_chat_id']}")
    warm_ui_route(composer_path)

    with open_mcp_page(f"{ui_url}{composer_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )

        hooked = client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        assert isinstance(hooked, dict) and hooked.get("hooked") is True, hooked

        focused = client.evaluate(
            page,
            """(() => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false };
  el.focus();
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )
        assert isinstance(focused, dict) and focused.get("ok") is True

        _type_react_controlled_text(client, page, "@chat:Alpha")
        wait_for_state(
            client,
            page,
            _MENTION_ALPHA_ITEM_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )
        clicked = client.evaluate(page, _CLICK_MENTION_ALPHA_ITEM_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        chip = wait_for_state(
            client,
            page,
            _MENTION_CHIP_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert chip.get("ready") is True, chip

        input_state = client.evaluate(page, _INPUT_VALUE_JS, timeout_sec=10.0)
        assert isinstance(input_state, dict) and input_state.get("ok") is True, input_state
        composer_value = str(input_state.get("value") or "").strip()
        assert "@chat:" in composer_value, input_state

        # Send the full composer text (keeps the @chat: token alive) plus a plain instruction.
        message = f"{composer_value} 请基于以上对话做简短总结"
        send_res = client.evaluate(
            page,
            f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-bridge' }};
  bridge.setActionMode?.('agent');
  const result = await bridge.sendChatMessage({json.dumps(message)}, {{ profile: 'live' }});
  return result;
}})()""",
            timeout_sec=60.0,
        )
        assert isinstance(send_res, dict) and send_res.get("ok") is True, send_res

        cap = wait_for_state(
            client,
            page,
            _CAPTURE_FILTERED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
        )
        assert cap.get("ready") is True, cap
        assert cap.get("hasPriorChat") is True, cap
        assert cap.get("hasWiki") is False, cap


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_zombie_prior_chat_mention_dropped_from_real_stream_payload() -> None:
    """Deleting the @chat token after selecting it must drop prior_chat from the real payload."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_prior_chat_fixture(api_url)
    composer_path = str(seeded.get("ui_path") or f"/{seeded['composer_chat_id']}")
    warm_ui_route(composer_path)

    with open_mcp_page(f"{ui_url}{composer_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        hooked = client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        assert isinstance(hooked, dict) and hooked.get("hooked") is True, hooked

        focused = client.evaluate(
            page,
            """(() => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false };
  el.focus();
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )
        assert isinstance(focused, dict) and focused.get("ok") is True

        _type_react_controlled_text(client, page, "@chat:Alpha")
        wait_for_state(
            client,
            page,
            _MENTION_ALPHA_ITEM_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )
        clicked = client.evaluate(page, _CLICK_MENTION_ALPHA_ITEM_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked
        chip = wait_for_state(
            client,
            page,
            _MENTION_CHIP_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert chip.get("ready") is True, chip

        # Wipe the composer: the selected reference is now a zombie (its token is gone).
        _type_react_controlled_text(client, page, "hello from e2e")

        send_res = client.evaluate(
            page,
            """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-bridge' };
  bridge.setActionMode?.('agent');
  const result = await bridge.sendChatMessage('hello from e2e', { profile: 'live' });
  return result;
})()""",
            timeout_sec=60.0,
        )
        assert isinstance(send_res, dict) and send_res.get("ok") is True, send_res

        cap = wait_for_state(
            client,
            page,
            _CAPTURE_FILTERED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
        )
        assert cap.get("ready") is True, cap
        assert cap.get("hasPriorChat") is False, cap
        assert cap.get("hasWiki") is False, cap


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_inline_wiki_mention_parsed_into_real_stream_payload() -> None:
    """A pasted `@wiki:Concept` token must be parsed into a wiki_concept payload reference."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_prior_chat_fixture(api_url)
    composer_path = str(seeded.get("ui_path") or f"/{seeded['composer_chat_id']}")
    warm_ui_route(composer_path)

    with open_mcp_page(f"{ui_url}{composer_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        hooked = client.evaluate(page, _FETCH_HOOK_JS, timeout_sec=10.0)
        assert isinstance(hooked, dict) and hooked.get("hooked") is True, hooked

        _type_react_controlled_text(client, page, "@wiki:AlphaProject 请总结该概念")

        send_res = client.evaluate(
            page,
            """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-bridge' };
  bridge.setActionMode?.('agent');
  const result = await bridge.sendChatMessage('@wiki:AlphaProject 请总结该概念', { profile: 'live' });
  return result;
})()""",
            timeout_sec=60.0,
        )
        assert isinstance(send_res, dict) and send_res.get("ok") is True, send_res

        cap = wait_for_state(
            client,
            page,
            _CAPTURE_FILTERED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
        )
        assert cap.get("ready") is True, cap
        assert cap.get("hasWiki") is True, cap
        wiki = next(
            (r for r in (cap.get("refs") or []) if r.get("type") == "wiki_concept"),
            None,
        )
        assert wiki is not None, cap
        assert wiki.get("concept_name") == "AlphaProject", cap
