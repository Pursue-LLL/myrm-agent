"""Chrome E2E: hyphenated slash command keeps the user-typed prefix (no LLM).

Regression for the unified `SLASH_COMMAND_SUFFIX_RE` (regex drift bug): a command
name containing a hyphen (e.g. `/systematic-d`) previously failed to be stripped
by the `\\w`-based suffix regex, wiping the user's prefix on skill activation and
blocking Escape dismissal. This test exercises the real composer with an agent
bound to the `systematic-debugging` skill (hyphenated id).
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

_SKILL_ID = "systematic-debugging"
_SLASH_QUERY = "systematic-d"


def _ensure_skill_enabled(api_url: str, skill_id: str) -> None:
    try:
        http_json(
            "POST",
            f"{api_url}/api/v1/skills/test/ensure-prebuilt-catalog",
            expected_statuses=frozenset({200, 201, 404}),
        )
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
}))()"""

_PALETTE_HYPHEN_ITEM_READY_JS = f"""(() => {{
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

_CLICK_HYPHEN_PALETTE_ITEM_JS = f"""(() => {{
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

_EXECUTE_STATE_JS = f"""(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  const snap = bridge?.turnSnapshot?.() ?? {{}};
  const input = document.querySelector('[data-chat-input]');
  const chips = document.querySelector('[data-testid="skill-activation-chips"]');
  const inputValue = input?.value ?? '';
  return {{
    ready:
      inputValue === 'fix it ' &&
      Boolean(chips) &&
      Array.isArray(snap.pendingSkillNames) &&
      snap.pendingSkillNames.includes({json.dumps(_SKILL_ID)}),
    inputValue,
    hasChips: Boolean(chips),
    pendingSkillNames: snap.pendingSkillNames ?? [],
    peekWire: bridge?.peekOutboundUserMessage?.() ?? '',
  }};
}})()"""

_PALETTE_ESCAPE_STATE_JS = """(() => {
  const input = document.querySelector('[data-chat-input]');
  const palette = document.querySelector('[data-testid="slash-command-palette"]');
  const inputValue = input?.value ?? '';
  return {
    ready: inputValue === 'fix it ' && !palette,
    inputValue,
    paletteGone: !palette,
  };
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
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return {{ ok: false, err: 'setter-not-found' }};
  setter.call(el, {json.dumps(text)});
  el.setSelectionRange(el.value.length, el.value.length);
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
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_hyphenated_slash_command_preserves_prefix_on_execute() -> None:
    """`fix it /systematic-d` executes the skill and keeps `fix it ` as the instruction."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _ensure_skill_enabled(api_url, _SKILL_ID)
    seeded = _seed_composer_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    agent_chat_path = f"/{chat_id}"
    warm_ui_route(agent_chat_path)

    with open_mcp_page(f"{ui_url}{agent_chat_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )

        client.evaluate(
            page,
            """(() => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false };
  el.focus();
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )

        _type_react_controlled_text(client, page, "fix it /systematic-d")
        wait_for_state(
            client,
            page,
            _PALETTE_HYPHEN_ITEM_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )

        clicked = client.evaluate(page, _CLICK_HYPHEN_PALETTE_ITEM_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        state = wait_for_state(
            client,
            page,
            _EXECUTE_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state.get("ready") is True, state
        assert state.get("inputValue") == "fix it ", state
        assert state.get("hasChips") is True, state
        assert _SKILL_ID in (state.get("pendingSkillNames") or []), state

        wire = client.evaluate(
            page,
            """(() => window.__MYRM_E2E_CHAT__?.peekOutboundUserMessage?.() ?? '')()""",
            timeout_sec=10.0,
        )
        assert isinstance(wire, str)
        assert wire.startswith(f"[use {_SKILL_ID}]"), wire
        assert "fix it" in wire


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_escape_dismisses_hyphenated_slash_command_and_keeps_prefix() -> None:
    """Escape closes a hyphenated slash palette and keeps `fix it ` (no raw prefix wipe)."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _ensure_skill_enabled(api_url, _SKILL_ID)
    seeded = _seed_composer_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    agent_chat_path = f"/{chat_id}"
    warm_ui_route(agent_chat_path)

    with open_mcp_page(f"{ui_url}{agent_chat_path}") as (client, page):
        wait_for_state(
            client,
            page,
            _COMPOSER_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )

        client.evaluate(
            page,
            """(() => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false };
  el.focus();
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )

        _type_react_controlled_text(client, page, "fix it /systematic-d")
        wait_for_state(
            client,
            page,
            _PALETTE_HYPHEN_ITEM_READY_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )

        escaped = client.evaluate(
            page,
            """(() => {
  const input = document.querySelector('[data-chat-input]');
  if (!input) return { ok: false, err: 'input-not-found' };
  input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', code: 'Escape', bubbles: true, cancelable: true }));
  return { ok: true };
})()""",
            timeout_sec=10.0,
        )
        assert isinstance(escaped, dict) and escaped.get("ok") is True, escaped

        state = wait_for_state(
            client,
            page,
            _PALETTE_ESCAPE_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert state.get("ready") is True, state
        assert state.get("inputValue") == "fix it ", state
        assert state.get("paletteGone") is True, state
