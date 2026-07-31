"""Chrome READ E2E: HITL clarify hydrate survives page reload (seed fixture, no LLM)."""

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
    assert str(seeded.get("variant") or "") == variant
    assert seeded.get("ui_path") == f"/{chat_id}"
    return seeded


def _pending_composer_state(chat_id: str) -> str:
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


def _structured_pending_composer_state(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {{}};
  const form = document.querySelector('[data-clarification-form="structured"]');
  const chatInput = document.querySelector('[data-chat-input]');
  return {{
    ready:
      snap.chatId === {chat_id_json} &&
      Boolean(form) &&
      !chatInput &&
      snap.clarificationAnswered !== true,
    chatId: snap.chatId ?? null,
    hasStructuredClarifyForm: Boolean(form),
    hasChatInput: Boolean(chatInput),
    clarificationAnswered: snap.clarificationAnswered === true,
  }};
}})()"""


def _answered_composer_state(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {{}};
  const form = document.querySelector('[data-clarification-form]');
  const chatInput = document.querySelector('[data-chat-input]');
  return {{
    ready:
      snap.chatId === {chat_id_json} &&
      Boolean(chatInput) &&
      !form &&
      snap.clarificationAnswered === true,
    chatId: snap.chatId ?? null,
    hasClarifyForm: Boolean(form),
    hasChatInput: Boolean(chatInput),
    clarificationAnswered: snap.clarificationAnswered === true,
  }};
}})()"""


def _assert_survives_reload(
    client,
    page,
    *,
    probe_js: str,
) -> None:
    first = wait_for_state(client, page, probe_js, timeout_sec=90.0)
    assert first.get("ready") is True, first

    client.reload(page, timeout_ms=60_000)
    after = wait_for_state(client, page, probe_js, timeout_sec=90.0)
    assert after.get("ready") is True, after


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_pending_survives_page_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "pending")
    chat_id = str(seeded["chat_id"])
    probe = _pending_composer_state(chat_id)

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        _assert_survives_reload(client, page, probe_js=probe)


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_answered_survives_page_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "answered")
    chat_id = str(seeded["chat_id"])
    probe = _answered_composer_state(chat_id)

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        _assert_survives_reload(client, page, probe_js=probe)


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_pending_with_regenerate_sibling_survives_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "regenerate_sibling")
    chat_id = str(seeded["chat_id"])
    probe = _pending_composer_state(chat_id)

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        _assert_survives_reload(client, page, probe_js=probe)


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_clarify_structured_form_pending_survives_page_reload() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_clarify_refresh_fixture(api_url, "structured_form")
    chat_id = str(seeded["chat_id"])
    probe = _structured_pending_composer_state(chat_id)

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        _assert_survives_reload(client, page, probe_js=probe)
