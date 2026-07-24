"""Real Chrome MCP E2E (READ lane): clarify hydrate survives page reload."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)


def _seed_clarify_refresh_fixture(api_url: str, variant: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-clarify-refresh-fixture?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eclarify")
    assert seeded.get("variant") == variant
    return seeded


_PENDING_CLARIFY_STATE = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {};
  const form = document.querySelector('[data-clarification-form]');
  const chatInput = document.querySelector('[data-chat-input]');
  return {
    ready: Boolean(snap.chatId) && Boolean(form) && !chatInput,
    chatId: snap.chatId ?? null,
    hasClarifyForm: Boolean(form),
    hasChatInput: Boolean(chatInput),
    clarificationAnswered: snap.clarificationAnswered === true,
  };
})()"""


_ANSWERED_CLARIFY_STATE = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {};
  const form = document.querySelector('[data-clarification-form]');
  const chatInput = document.querySelector('[data-chat-input]');
  const answeredBanner = Array.from(document.querySelectorAll('span')).some((node) =>
    /Clarification answered|已回答澄清问题/i.test((node.textContent || '').trim()),
  );
  return {
    ready:
      Boolean(snap.chatId) &&
      !form &&
      Boolean(chatInput) &&
      (snap.clarificationAnswered === true || answeredBanner),
    chatId: snap.chatId ?? null,
    hasClarifyForm: Boolean(form),
    hasChatInput: Boolean(chatInput),
    clarificationAnswered: snap.clarificationAnswered === true,
    hasAnsweredBanner: answeredBanner,
  };
})()"""


def _regenerate_sibling_state(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {{}};
  const form = document.querySelector('[data-clarification-form]');
  const chatInput = document.querySelector('[data-chat-input]');
  return {{
    ready:
      snap.chatId === {chat_id_json} &&
      Boolean(form) &&
      !chatInput &&
      snap.clarificationAnswered !== true,
    chatId: snap.chatId ?? null,
    hasClarifyForm: Boolean(form),
    hasChatInput: Boolean(chatInput),
    clarificationAnswered: snap.clarificationAnswered === true,
  }};
}})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_pending_survives_page_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "pending")
    chat_id = str(seeded["chat_id"])

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        first_state = wait_for_state(
            client,
            page,
            _PENDING_CLARIFY_STATE,
            timeout_sec=90.0,
        )
        assert first_state.get("ready") is True
        assert first_state.get("hasClarifyForm") is True
        assert first_state.get("hasChatInput") is False

        client.reload(page, timeout_ms=60_000)
        reloaded_state = wait_for_state(
            client,
            page,
            _PENDING_CLARIFY_STATE,
            timeout_sec=90.0,
        )
        assert reloaded_state.get("ready") is True
        assert reloaded_state.get("hasClarifyForm") is True


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_answered_survives_page_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "answered")
    chat_id = str(seeded["chat_id"])

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        first_state = wait_for_state(
            client,
            page,
            _ANSWERED_CLARIFY_STATE,
            timeout_sec=90.0,
        )
        assert first_state.get("ready") is True
        assert first_state.get("hasClarifyForm") is False
        assert first_state.get("hasChatInput") is True

        client.reload(page, timeout_ms=60_000)
        reloaded_state = wait_for_state(
            client,
            page,
            _ANSWERED_CLARIFY_STATE,
            timeout_sec=90.0,
        )
        assert reloaded_state.get("ready") is True
        assert reloaded_state.get("clarificationAnswered") is True


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_pending_with_regenerate_sibling_survives_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "regenerate_sibling")
    chat_id = str(seeded["chat_id"])
    state_js = _regenerate_sibling_state(chat_id)

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        first_state = wait_for_state(
            client,
            page,
            state_js,
            timeout_sec=90.0,
        )
        assert first_state.get("ready") is True
        assert first_state.get("hasClarifyForm") is True

        client.reload(page, timeout_ms=60_000)
        reloaded_state = wait_for_state(
            client,
            page,
            state_js,
            timeout_sec=90.0,
        )
        assert reloaded_state.get("ready") is True
        assert reloaded_state.get("hasClarifyForm") is True
