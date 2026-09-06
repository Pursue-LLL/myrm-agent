"""Chrome READ E2E: slash skill activation chip UX (O1-lite, no LLM on composer path)."""

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

_SKILL_ID = "systematic-debugging"
_SLASH_QUERY = "systematic"


def _ensure_skill_enabled(api_url: str, skill_id: str) -> None:
    try:
        catalog = http_json(
            "POST",
            f"{api_url}/api/v1/skills/test/ensure-prebuilt-catalog",
            expected_statuses=frozenset({200, 201, 404}),
        )
        if isinstance(catalog, dict) and catalog.get("contains_systematic_debugging") is not True:
            # Slash palette can fall back to agent-bound skill ids when catalog is empty.
            pass
    except RuntimeError:
        pass

    config = http_json("GET", f"{api_url}/api/v1/skills/config")
    assert isinstance(config, dict)
    enabled = list(config.get("enabled_prebuilt_ids") or [])
    if skill_id in enabled:
        return
    enabled.append(skill_id)
    http_json(
        "PUT",
        f"{api_url}/api/v1/skills/config",
        {"enabled_prebuilt_ids": enabled},
    )


def _seed_composer_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-skill-chip-composer-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    agent_id = str(seeded.get("agent_id") or "")
    assert chat_id.startswith("e2eslashchip")
    assert agent_id
    return seeded


_COMPOSER_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-chat-input]') &&
    !!window.__MYRM_E2E_CHAT__ &&
    (window.__MYRM_E2E_CHAT__.turnSnapshot?.()?.agentSelectedSkillCount ?? 0) > 0,
  hasInput: !!document.querySelector('[data-chat-input]'),
  hasBridge: !!window.__MYRM_E2E_CHAT__,
  agentSelectedSkillCount:
    window.__MYRM_E2E_CHAT__?.turnSnapshot?.()?.agentSelectedSkillCount ?? 0,
}))()"""

_SKILL_PALETTE_ITEM_READY_JS = f"""(() => {{
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  if (!palette) return {{ ready: false, reason: 'no-palette' }};
  const needle = {json.dumps(_SLASH_QUERY)};
  const items = Array.from(palette.querySelectorAll('[cmdk-item], [role="option"]'));
  const target = items.find((el) => (el.textContent || '').toLowerCase().includes(needle));
  return {{
    ready: Boolean(target),
    itemCount: items.length,
    sample: items.slice(0, 5).map((el) => (el.textContent || '').slice(0, 80)),
  }};
}})()"""

_CLICK_SKILL_PALETTE_ITEM_JS = f"""(() => {{
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  if (!palette) return {{ ok: false, reason: 'no-palette' }};
  const needle = {json.dumps(_SLASH_QUERY)};
  const items = Array.from(palette.querySelectorAll('[cmdk-item], [role="option"]'));
  const target = items.find((el) => (el.textContent || '').toLowerCase().includes(needle));
  if (!target) {{
    return {{
      ok: false,
      reason: 'no-skill-item',
      sample: items.slice(0, 5).map((el) => (el.textContent || '').slice(0, 80)),
    }};
  }}
  target.click();
  return {{ ok: true }};
}})()"""

_CHIP_COMPOSER_STATE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {};
  const input = document.querySelector('[data-chat-input]');
  const chips = document.querySelector('[data-testid="skill-activation-chips"]');
  const inputValue = input?.value ?? '';
  return {
    ready:
      Boolean(chips) &&
      Array.isArray(snap.pendingSkillNames) &&
      snap.pendingSkillNames.length > 0 &&
      !inputValue.trimStart().startsWith('[use '),
    hasChips: Boolean(chips),
    inputValue,
    inputHasUsePrefix: inputValue.trimStart().startsWith('[use '),
    pendingSkillNames: snap.pendingSkillNames ?? [],
    peekWire: bridge?.peekOutboundUserMessage?.() ?? '',
  };
})()"""

_TRANSCRIPT_MESSAGES_READY_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  return {
    ready: (snap.userCount ?? 0) > 0,
    userCount: snap.userCount ?? 0,
    hasBridge: !!window.__MYRM_E2E_CHAT__,
  };
})()"""

_TRANSCRIPT_CHIP_STATE_JS = """(() => {
  const chips = document.querySelector('[data-testid="skill-activation-chips"]');
  const userBubble = document.querySelector('[data-message-id]');
  const text = (userBubble?.textContent || '').trim();
  return {
    ready: Boolean(chips) && Boolean(text) && !/\\[use\\s/i.test(text),
    hasChips: Boolean(chips),
    userVisibleText: text,
    hasRawUsePrefix: /\\[use\\s/i.test(text),
  };
})()"""


def _seed_transcript_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-skill-chip-transcript-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2eskillchip")
    return seeded


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_slash_skill_palette_sets_composer_chip_without_raw_use_prefix() -> None:
    """Slash skill pick shows chip; composer hides `[use]`; wire preview includes skill prefix."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _ensure_skill_enabled(api_url, _SKILL_ID)
    seeded = _seed_composer_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    agent_id = str(seeded["agent_id"])
    agent_chat_path = str(seeded.get("ui_path") or f"/{chat_id}?agentId={agent_id}")
    warm_ui_route(agent_chat_path)

    with open_mcp_page(f"{ui_url}{agent_chat_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )

        input_el = client.evaluate(
            page,
            """(() => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false };
  el.focus();
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )
        assert isinstance(input_el, dict) and input_el.get("ok") is True

        # Fill the React-controlled TextareaAutosize via native value setter +
        # input event. CDP `type_text` (Input.insertText) does not reliably
        # update React-controlled inputs, leaving `inputMessage` empty so the
        # slash palette never opens.
        typed = client.evaluate(
            page,
            f"""(() => {{
  const el = document.querySelector('[data-chat-input]');
  if (!el) return {{ ok: false, err: 'input-not-found' }};
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {json.dumps("/" + _SLASH_QUERY)});
  el.setSelectionRange(el.value.length, el.value.length);
  el.dispatchEvent(new Event('input', {{ bubbles: true }}));
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return {{ ok: true, value: el.value }};
}})()""",
            timeout_sec=10.0,
        )
        assert isinstance(typed, dict) and typed.get("ok") is True, typed
        wait_for_state(
            client,
            page,
            _SKILL_PALETTE_ITEM_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )

        clicked = client.evaluate(page, _CLICK_SKILL_PALETTE_ITEM_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        state = wait_for_state(
            client,
            page,
            _CHIP_COMPOSER_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state.get("hasChips") is True, state
        assert state.get("inputHasUsePrefix") is False, state
        assert _SKILL_ID in (state.get("pendingSkillNames") or []), state

        client.evaluate(
            page,
            """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.setInputMessage?.('analyze this bug');
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )

        wire = client.evaluate(
            page,
            """(() => window.__MYRM_E2E_CHAT__?.peekOutboundUserMessage?.() ?? '')()""",
            timeout_sec=10.0,
        )
        assert isinstance(wire, str)
        assert wire.startswith(f"[use {_SKILL_ID}]"), wire
        assert "analyze this bug" in wire


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_transcript_hides_skill_wire_prefix_and_shows_chip() -> None:
    """Persisted `[use skill]` user messages render chips + stripped user text in transcript."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_transcript_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    user_text = str(seeded["user_text"])
    ui_path = str(seeded.get("ui_path") or f"/{chat_id}")
    warm_ui_route(ui_path)

    with open_mcp_page(f"{ui_url}{ui_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _TRANSCRIPT_MESSAGES_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        state = wait_for_state(
            client,
            page,
            _TRANSCRIPT_CHIP_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("hasChips") is True, state
        assert state.get("hasRawUsePrefix") is False, state
        assert user_text in str(state.get("userVisibleText") or ""), state
