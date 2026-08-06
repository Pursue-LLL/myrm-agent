"""Chrome READ E2E: composer @chat: mention + Cmd+K cite-to-composer (no LLM)."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
    _warm_ui_parallel_wait_sec,
)

_PRIOR_TITLE_FRAGMENT = "Alpha project"


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

_MENTION_CHIP_READY_JS = f"""(() => {{
  const chips = Array.from(document.querySelectorAll('[data-chat-composer] .rounded-full'));
  const hasPriorChip = chips.some((el) => (el.textContent || '').includes({json.dumps(_PRIOR_TITLE_FRAGMENT)}));
  const store = window.__myrmChatStore?.getState?.();
  const mentions = Array.isArray(store?.mentionReferences) ? store.mentionReferences : [];
  const hasPriorMention = mentions.some((m) => m?.type === 'prior_chat');
  return {{
    ready: hasPriorChip && hasPriorMention,
    chipCount: chips.length,
    mentionTypes: mentions.map((m) => m?.type),
    chipTexts: chips.map((el) => (el.textContent || '').slice(0, 120)),
  }};
}})()"""

_CLICK_MENTION_ITEM_JS = """(() => {
  const item = document.querySelector('[data-mention-item]');
  if (!item) return { ok: false, reason: 'no-mention-item' };
  item.click();
  return { ok: true };
})()"""

_OPEN_SEARCH_DIALOG_JS = """(() => {
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
  let input = document.querySelector('[data-search-input]');
  if (!input) {
    const trigger = document.querySelector('[data-search-trigger]');
    if (trigger instanceof HTMLElement) {
      trigger.click();
    }
    input = document.querySelector('[data-search-input]');
  }
  if (input instanceof HTMLInputElement) {
    input.focus();
  }
  return {
    ready: Boolean(input),
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


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
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

        client.type_text(page, "@chat:Alpha")
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


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
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

        opened = client.evaluate(page, _OPEN_SEARCH_DIALOG_JS, timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ready") is True, opened

        focus_state = wait_for_state(
            client,
            page,
            _SEARCH_INPUT_FOCUSED_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(15.0),
        )
        assert focus_state.get("ready") is True, focus_state

        client.type_text(page, "Alpha")
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


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
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

        client.type_text(page, "@chat:Alpha")
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
