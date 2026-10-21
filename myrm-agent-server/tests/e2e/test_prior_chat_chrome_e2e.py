"""Chrome READ E2E: composer @chat: mention + Cmd+K cite-to-composer (no LLM)."""

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

_PRIOR_TITLE_FRAGMENT = "Alpha project"


def _type_react_controlled_text(
    client: object,
    page: object,
    text: str,
    *,
    selector: str = "[data-chat-input]",
) -> dict[str, object]:
    """Fill React-controlled input via native setter + input event (CDP type_text is unreliable)."""
    result = client.evaluate(  # type: ignore[attr-defined]
        page,
        f"""(() => {{
  const el = document.querySelector({json.dumps(selector)});
  if (!el) return {{ ok: false, err: 'input-not-found', selector: {json.dumps(selector)} }};
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


def _seed_prior_chat_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-prior-chat-fixture")
    assert isinstance(seeded, dict)
    composer_chat_id = str(seeded.get("composer_chat_id") or "")
    assert composer_chat_id.startswith("e2ecomp")
    return seeded


_COMPOSER_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-chat-input]') && !!window.__MYRM_E2E_CHAT__,
  hasInput: !!document.querySelector('[data-chat-input]'),
  hasBridge: !!window.__MYRM_E2E_CHAT__,
}))()"""

_MENTION_ITEM_READY_JS = """(() => {
  const item = document.querySelector('[data-mention-item]');
  return { ready: Boolean(item), itemText: (item?.textContent || '').slice(0, 120) };
})()"""

_MENTION_ALPHA_ITEM_READY_JS = """(() => {
  const items = Array.from(document.querySelectorAll('[data-mention-item]'));
  const match = items.find((item) => (item.textContent || '').includes('Alpha'));
  return {
    ready: Boolean(match),
    itemText: (match?.textContent || '').slice(0, 120),
    count: items.length,
  };
})()"""

_MENTION_CHIP_READY_JS = f"""(() => {{
  const store = window.__myrmChatStore?.getState?.();
  const mentions = Array.isArray(store?.mentionReferences) ? store.mentionReferences : [];
  const priorMention = mentions.find((m) => m?.type === 'prior_chat');
  const label = String(priorMention?.label || '');
  const hasAlpha = label.includes({json.dumps(_PRIOR_TITLE_FRAGMENT.split()[0])});
  return {{
    ready: Boolean(priorMention) && hasAlpha,
    mentionTypes: mentions.map((m) => m?.type),
    priorLabel: label.slice(0, 120),
  }};
}})()"""

_CLICK_MENTION_ITEM_JS = """(() => {
  const item = document.querySelector('[data-mention-item]');
  if (!item) return { ok: false, reason: 'no-mention-item' };
  item.click();
  return { ok: true };
})()"""

_CLICK_MENTION_ALPHA_ITEM_JS = """(() => {
  const items = Array.from(document.querySelectorAll('[data-mention-item]'));
  const match = items.find((item) => (item.textContent || '').includes('Alpha'));
  if (!match) return { ok: false, reason: 'no-alpha-mention-item', count: items.length };
  match.click();
  return { ok: true };
})()"""

_OPEN_SEARCH_DIALOG_JS = """(() => {
  const trigger = document.querySelector('[data-search-trigger]');
  if (trigger instanceof HTMLElement) {
    trigger.click();
  } else {
    window.dispatchEvent(
      new KeyboardEvent('keydown', {
        key: 'k',
        code: 'KeyK',
        metaKey: true,
        ctrlKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );
  }
  const input = document.querySelector('[data-search-input]');
  if (input instanceof HTMLInputElement) {
    input.focus();
  }
  return {
    ready: Boolean(input),
    hasTrigger: Boolean(trigger),
    focused: document.activeElement === input,
  };
})()"""

_SEARCH_INPUT_FOCUSED_JS = """(() => {
  const input = document.querySelector('[data-search-input]');
  if (!(input instanceof HTMLInputElement)) {
    return { ready: false, reason: 'no-search-input' };
  }
  if (document.activeElement !== input) {
    input.focus();
  }
  return {
    ready: document.activeElement === input,
    value: input.value.slice(0, 80),
  };
})()"""

_SEARCH_CITE_READY_JS = """(() => {
  const cite = document.querySelector('[data-cite-to-composer]');
  return {
    ready: Boolean(cite),
    citeText: (cite?.textContent || '').slice(0, 120),
  };
})()"""

_CLICK_SEARCH_CITE_JS = """(() => {
  const cite = document.querySelector('[data-cite-to-composer]');
  if (!cite) return { ok: false, reason: 'no-cite-button' };
  cite.click();
  return { ok: true };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_prior_chat_mention_chip_chrome_e2e() -> None:
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
            _MENTION_ITEM_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )

        clicked = client.evaluate(page, _CLICK_MENTION_ITEM_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        state = wait_for_state(
            client,
            page,
            _MENTION_CHIP_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state.get("ready") is True, state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_prior_chat_cmdk_cite_chrome_e2e() -> None:
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

        client.evaluate(page, _OPEN_SEARCH_DIALOG_JS, timeout_sec=15.0)
        focus_state = wait_for_state(
            client,
            page,
            _SEARCH_INPUT_FOCUSED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert focus_state.get("ready") is True, focus_state

        _type_react_controlled_text(client, page, "Alpha", selector="[data-search-input]")
        wait_for_state(
            client,
            page,
            _SEARCH_CITE_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )

        clicked = client.evaluate(page, _CLICK_SEARCH_CITE_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        state = wait_for_state(
            client,
            page,
            _MENTION_CHIP_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state.get("ready") is True, state


_EMPTY_CHAT_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-chat-input]'),
  hasComposerBridge: !!window.__MYRM_E2E_CHAT__,
  chatId: window.__myrmChatStore?.getState?.()?.chatId ?? null,
}))()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_prior_chat_mention_empty_chat_home_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _seed_prior_chat_fixture(api_url)
    warm_ui_route("/")

    with open_mcp_page(f"{ui_url}/") as (client, page):
        empty_state = wait_for_state(
            client,
            page,
            _EMPTY_CHAT_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert empty_state.get("ready") is True, empty_state

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
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )

        clicked = client.evaluate(page, _CLICK_MENTION_ALPHA_ITEM_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        state = wait_for_state(
            client,
            page,
            _MENTION_CHIP_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
        )
        assert state.get("ready") is True, state
